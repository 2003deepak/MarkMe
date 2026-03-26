from bson import DBRef, ObjectId
from fastapi import Request
from fastapi.responses import JSONResponse
from app.models.allModel import StudentBasicView, StudentSelectionRequest
from app.schemas.student import Student
from app.schemas.subject import Subject
from app.schemas.teacher import Teacher
from app.core.redis import redis_client
import json


# TODO:
# Currently subjects do not store academic_year or batch information.
# So students are matched using only:
#   program + department + semester
#
# When academic_year is introduced in the Subject schema,
# the filter should be updated to include:
#
#   program + department + semester + academic_year
#
# Example future filter:
#
# {
#   "program": s.program,
#   "department": s.department,
#   "semester": s.semester,
#   "academic_year": s.academic_year
# }
#
# This will prevent teachers from seeing students from old batches.

async def get_students_by_teacher(request: Request, student_request: StudentSelectionRequest):

    #auth check
    if request.state.user.get("role") != "teacher":
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Only teachers can access this route"}
        )

    teacher_id = request.state.user.get("id")

    cache_key = (
        f"teacher_students:{teacher_id}:"
        f"{student_request.batch_year}:{student_request.program}:"
        f"{student_request.semester}:{student_request.name}:"
        f"{student_request.page}:{student_request.limit}"
    )

    cached = await redis_client.get(cache_key)

    if cached:
        data = json.loads(cached)
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Students fetched from cache",
                "data": data["records"],
                "total": data["total"],
                "source": "cache"
            }
        )

    #fetch teacher
    teacher = await Teacher.find_one(Teacher.id == ObjectId(teacher_id))

    if not teacher:
        return JSONResponse(
            status_code=404,
            content={"success": False, "message": "Teacher not found"}
        )

    #fetch subjects taught by teacher
    teacher_subjects = await Subject.find(
        {"teacher_assigned.$id": teacher.id}
    ).to_list()

    if not teacher_subjects:
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": [],
                "total": 0
            }
        )

    #extract program + department + semester combinations
    class_filters = []

    subject_map = {}

    for s in teacher_subjects:

        class_filters.append({
            "program": s.program,
            "department": s.department,
            "semester": s.semester
        })

        key = (s.program, s.department, s.semester)

        subject_map.setdefault(key, []).append({
            "subject_code": s.subject_code,
            "subject_name": s.subject_name
        })

    #remove duplicate filters
    class_filters = [dict(t) for t in {tuple(d.items()) for d in class_filters}]

    filters = {
        "$or": class_filters,
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

    #pagination
    skip = (student_request.page - 1) * student_request.limit
    limit = student_request.limit

    total_students = await Student.find(filters).count()

    students = (
        await Student.find(filters)
        .project(StudentBasicView)
        .sort(+Student.roll_number)
        .skip(skip)
        .limit(limit)
        .to_list()
    )

    enriched_students = []

    for student in students:

        student_dict = json.loads(student.json())

        key = (student.program, student.department, student.semester)

        student_dict["subjects_taught_by_teacher"] = subject_map.get(key, [])

        enriched_students.append(student_dict)

    #cache for 30 minutes
    await redis_client.setex(
        cache_key,
        1800,
        json.dumps({
            "records": enriched_students,
            "total": total_students
        })
    )

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "Students fetched successfully",
            "data": enriched_students,
            "total": total_students,
            "source": "database"
        }
    )


async def class_based_teacher(request: Request):

    user = request.state.user

    if not user or user.get("role") != "teacher":
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "message": "Only teachers can access this route"
            }
        )

    teacher_id = user.get("id")

    if not teacher_id:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "Teacher ID missing in token"
            }
        )

    try:
        teacher_oid = ObjectId(teacher_id)
    except Exception:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "Invalid teacher ID"
            }
        )

    pipeline = [

        # find subjects assigned to teacher
        {
            "$match": {
                "teacher_assigned.$id": teacher_oid
            }
        },

        # group by program + department + semester
        {
            "$group": {
                "_id": {
                    "program": "$program",
                    "department": "$department",
                    "semester": "$semester"
                },

                "subjects": {
                    "$push": {
                        "subject_id": {"$toString": "$_id"},
                        "subject_name": "$subject_name",
                        "subject_code": "$subject_code",
                        "component": "$component"
                    }
                }
            }
        },

        {
            "$project": {
                "_id": 0,
                "program": "$_id.program",
                "department": "$_id.department",
                "semester": "$_id.semester",
                "subjects": 1
            }
        },

        {
            "$sort": {
                "program": 1,
                "semester": 1
            }
        }

    ]

    try:

        classes = await Subject.aggregate(pipeline).to_list(length=100)

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Teacher classes fetched successfully",
                "total_classes": len(classes),
                "data": classes
            }
        )

    except Exception as e:

        print("Teacher class fetch error:", e)

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "Failed to fetch classes"
            }
        )