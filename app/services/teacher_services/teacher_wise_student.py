from bson import DBRef, ObjectId
from fastapi import Request
from fastapi.responses import JSONResponse
from app.models.allModel import StudentBasicView, StudentSelectionRequest
from app.schemas.student import Student
from app.schemas.subject import Subject
from app.schemas.teacher import Teacher
from app.core.redis import redis_client
import json


async def get_students_by_teacher(request: Request, student_request: StudentSelectionRequest):

    # 1. Auth check
    user_role = request.state.user.get("role")
    if user_role != "teacher":
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Only teachers can access this route"}
        )

    teacher_email = request.state.user.get("email")

    # Create cache key based on request filters
    cache_key = (
        f"teacher_students:{teacher_email}:"
        f"{student_request.batch_year}:"
        f"{student_request.program}:"
        f"{student_request.semester}:"
        f"{student_request.name}:"
        f"{student_request.page}:{student_request.limit}"
    )

    # 2. Redis cache check
    cached = await redis_client.get(cache_key)
    if cached:
        data = json.loads(cached)
        return JSONResponse(status_code=200, content={
            "success": True,
            "message": "Students fetched from cache",
            "data": data["records"],
            "total": data["total"],
            "source": "cache"
        })

    # 3. Fetch teacher
    teacher = await Teacher.find_one(Teacher.email == teacher_email)
    if not teacher:
        return JSONResponse(
            status_code=404,
            content={"success": False, "message": "Teacher not found"}
        )

    department = teacher.department

    # 4. Build filter query
    filters = {
        "department": department,
        "is_verified": True
    }

    if student_request.batch_year:
        filters["batch_year"] = student_request.batch_year

    if student_request.program:
        filters["program"] = student_request.program

    if student_request.semester:
        filters["semester"] = student_request.semester

    if student_request.name:
        filters["first_name"] = {"$regex": student_request.name, "$options": "i"}

    # 5. Pagination
    skip = (student_request.page - 1) * student_request.limit
    limit = student_request.limit

    # 6. Total count
    total_students = await Student.find(filters).count()

    # 7. Fetch paginated students
    students = (
        await Student.find(filters)
        .project(StudentBasicView)
        .sort(+Student.roll_number)
        .skip(skip)
        .limit(limit)
        .to_list()
    )

    # 8. Subjects taught by teacher
    teacher_subjects = await Subject.find(
        {"teacher_assigned.$id": teacher.id}
    ).to_list()

    subject_map = {
        (s.program, s.semester): {
            "subject_code": s.subject_code,
            "subject_name": s.subject_name
        }
        for s in teacher_subjects
    }

    # 9. Add subjects taught by teacher
    enriched_students = []
    for student in students:
        student_dict = json.loads(student.json())

        key = (student.program, student.semester)
        student_dict["subjects_taught_by_teacher"] = (
            [subject_map[key]] if key in subject_map else []
        )

        enriched_students.append(student_dict)

    # 10. Save result in Redis (30 minutes)
    await redis_client.setex(
        cache_key, 1800,
        json.dumps({"records": enriched_students, "total": total_students})
    )

    # 11. Response
    return JSONResponse(status_code=200, content={
        "success": True,
        "message": "Students fetched successfully",
        "data": enriched_students,
        "total": total_students,
        "source": "database"
    })


async def class_based_teacher(request: Request):

    # 1. Auth Check
    user = request.state.user
    if not user or user.get("role") != "teacher":
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Only teachers can access this route"}
        )

    teacher_id = user.get("id")
    teacher_dept = user.get("department")  # <-- department from token

    if not teacher_id:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Teacher ID not found in token"}
        )

    if not teacher_dept:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Department missing in token"}
        )

    try:
        teacher_oid = ObjectId(teacher_id)
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Invalid teacher ID format"}
        )

    # 2. Mongo Pipeline
    pipeline = [
        {
            "$match": {
                "teacher_assigned.$id": teacher_oid
            }
        },
        {
            "$lookup": {
                "from": "students",
                "let": {"prog": "$program", "sem": "$semester"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {
                                "$and": [
                                    {"$eq": ["$program", "$$prog"]},
                                    {"$eq": ["$semester", "$$sem"]}
                                ]
                            }
                        }
                    }
                ],
                "as": "students_in_class"
            }
        },
        {
            "$group": {
                "_id": {
                    "program": "$program",
                    "semester": "$semester"
                },
                "subjects": {
                    "$push": {
                        "subject_name": "$subject_name",
                        "subject_code": "$subject_code",
                        "component": "$component"
                    }
                },
                "students_in_class": {"$first": "$students_in_class"}
            }
        },
        {
            "$project": {
                "_id": 0,
                "program": "$_id.program",
                "semester": "$_id.semester",
                "subjects": 1,
                "student_count": {"$size": "$students_in_class"}
            }
        },
        {"$sort": {"program": 1, "semester": 1}}
    ]

    # 3. Execute pipeline
    try:
        cursor = Subject.aggregate(pipeline)
        class_list = await cursor.to_list(length=100)

        # 4. Inject department into every class object
        for cls in class_list:
            cls["department"] = teacher_dept   # <-- insert here

        # 5. Return response
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Classes fetched successfully",
                "total_classes": len(class_list),
                "data": class_list
            }
        )

    except Exception as e:
        print(f"Error fetching teacher classes: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "Failed to fetch classes"}
        )
