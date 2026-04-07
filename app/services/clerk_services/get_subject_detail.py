from typing import Optional
from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from bson import ObjectId
from datetime import datetime
import json

from app.core.redis import get_redis_client
from app.schemas.subject import Subject
from app.models.allModel import SubjectShortView


#mongo encoder
class MongoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


async def list_all_subjects(
    request: Request,
    department: Optional[str] = None,
    program: Optional[str] = None,
    semester: Optional[int] = None,
    page: int = 1,
    limit: int = 10
):
    user = request.state.user
    role = user.get("role")

    #auth
    if role != "clerk":
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "message": "You are not authorized to access subjects"
            }
        )

    scopes = user.get("academic_scopes", [])

    if not scopes:
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "No subjects found",
                "data": [],
                "pagination": {}
            }
        )

    #extract scope filters
    program_ids = [s["program_id"] for s in scopes]
    department_ids = [s["department_id"] for s in scopes]

    match_stage = {
        "program": {"$in": program_ids},
        "department": {"$in": department_ids}
    }

    #apply UI filters (safe)
    if program and program in program_ids:
        match_stage["program"] = program

    if department and department in department_ids:
        match_stage["department"] = department

    if semester:
        match_stage["semester"] = semester

    skip = (page - 1) * limit

    pipeline = [
        {
            "$match": match_stage
        },

        #lookup teacher
        {
            "$lookup": {
                "from": "teachers",
                "localField": "teacher_assigned.$id",
                "foreignField": "_id",
                "as": "teacher"
            }
        },

        #unwind teacher (one-to-one)
        {
            "$unwind": {
                "path": "$teacher",
                "preserveNullAndEmptyArrays": True
            }
        },

        #project clean response
        {
            "$project": {
                "_id": 1,
                "subject_name": 1,
                "subject_code": 1,
                "program": 1,
                "department": 1,
                "semester": 1,
                "credit": 1,
                "component": 1,

                #teacher fields
                "teacher": {
                    "_id": "$teacher._id",
                    "first_name": "$teacher.first_name",
                    "last_name": "$teacher.last_name",
                    "email": "$teacher.email",
                    "teacher_id": "$teacher.teacher_id"
                },
            }
        },

        #facet for pagination
        {
            "$facet": {
                "data": [
                    {"$skip": skip},
                    {"$limit": limit}
                ],
                "totalCount": [
                    {"$count": "count"}
                ]
            }
        }
    ]

    result = await Subject.aggregate(pipeline).to_list()

    if not result:
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "No subjects found",
                "data": [],
                "pagination": {}
            }
        )

    data = result[0].get("data", [])
    total_count = result[0].get("totalCount", [])
    total = total_count[0]["count"] if total_count else 0

    #format response
    def serialize(doc):
        doc["_id"] = str(doc["_id"])

        if doc.get("teacher") and doc["teacher"].get("_id"):
            doc["teacher"]["_id"] = str(doc["teacher"]["_id"])

        if doc.get("created_at"):
            doc["created_at"] = doc["created_at"].isoformat()

        if doc.get("updated_at"):
            doc["updated_at"] = doc["updated_at"].isoformat()

        return doc

    response_data = [serialize(d) for d in data]

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "Subject details fetched successfully",
            "data": response_data,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "total_pages": (total + limit - 1) // limit
            }
        }
    )
    
async def get_assignable_subjects(request: Request):

    user = request.state.user
    role = user.get("role")

    #auth
    if role != "clerk":
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "message": "You are not authorized to access subjects"
            }
        )
        
    redis = await get_redis_client()

    scopes = user.get("academic_scopes", [])

    if not scopes:
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "No subjects found",
                "data": []
            }
        )

    program_ids = [s["program_id"] for s in scopes]
    department_ids = [s["department_id"] for s in scopes]

    # cache key (based on scope)
    scope_key = "_".join(sorted([f"{d}:{p}" for d, p in zip(department_ids, program_ids)]))
    cache_key = f"assignable_subjects:{user.get('email')}"

    cached = await redis.get(cache_key)
    if cached:
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Assignable subjects fetched successfully (cache)",
                "data": json.loads(cached)
            }
        )

    #aggregation pipeline
    pipeline = [
        {
            "$match": {
                "program": {"$in": program_ids},
                "department": {"$in": department_ids}
            }
        },

        #lookup teacher
        {
            "$lookup": {
                "from": "teachers",
                "localField": "teacher_assigned.$id",
                "foreignField": "_id",
                "as": "teacher"
            }
        },

        {
            "$unwind": {
                "path": "$teacher",
                "preserveNullAndEmptyArrays": True
            }
        },

        {
            "$project": {
                "_id": 1,
                "subject_name": 1,
                "subject_code": 1,
                "component": 1,
                "program": 1,
                "department": 1,
                "semester": 1,

                "teacher": {
                    "_id": "$teacher._id",
                    "first_name": "$teacher.first_name",
                    "last_name": "$teacher.last_name"
                }
            }
        }
    ]

    subjects = await Subject.aggregate(pipeline).to_list()

    if not subjects:
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "No subjects found",
                "data": []
            }
        )

    # grouping
    grouped = {}

    for sub in subjects:
        group_key = f"{sub['department']} - {sub['program']} (Sem {sub['semester']})"

        if group_key not in grouped:
            grouped[group_key] = []

        teacher = sub.get("teacher")

        grouped[group_key].append({
            "id": str(sub["_id"]),
            "label": f"{sub['subject_name']} ({sub['component']})",
            "code": sub.get("subject_code"),
            "component": sub.get("component"),

            "assigned": bool(teacher and teacher.get("_id")),

            "teacher_name": (
                f"{teacher.get('first_name','')} {teacher.get('last_name','')}".strip()
                if teacher and teacher.get("_id")
                else None
            )
        })

    response = [
        {
            "group": group,
            "subjects": subs
        }
        for group, subs in grouped.items()
    ]

    # cache it
    await redis.setex(
        cache_key,
        300,
        json.dumps(response, cls=MongoJSONEncoder)
    )

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "Assignable subjects fetched successfully",
            "data": response
        }
    )

async def get_subject_by_id(request : Request , subject_id: str):
    
    subject_id = subject_id.upper()
    user_email = request.state.user.get("email")
    user_role = request.state.user.get("role")

    if user_role != "clerk":
        print("❌ Access denied: Not a clerk")
        
        return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "message": "Only Clerk can access this route"
                }
            )

    clerk_program = request.state.user.get("program")
    print(f"➡️ Requested by: {user_email} (Role: {user_role}, Program: {clerk_program})")


    # Query all subjects by subject_code and program, and fetch linked teacher data
    subjects = await Subject.find(
        Subject.subject_code == subject_id,
        Subject.program == clerk_program,
        fetch_links=True  
    ).project(SubjectShortView).to_list()

    if not subjects:
        print(f"❌ Subjects not found: {subject_id} in Program {clerk_program}")

        
        return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "message": f"No subjects found with ID {subject_id} in Program {clerk_program}"
                }
            )

    # Wrap in dict for response and Redis
    subject_data = {
        "program": clerk_program,
        "subject_code": subject_id,
        "subjects": [subject.dict() for subject in subjects]
    }


    # Use jsonable_encoder for response

    return JSONResponse(
                    status_code=200,
                    content={
                        "success": True,
                        "message" : "Subject Details fetched successfully",
                        "data": jsonable_encoder(subject_data, custom_encoder={ObjectId: str, datetime: lambda x: x.isoformat()})
                    }
                )



async def get_timetable_subjects(
    request: Request,
    department: Optional[str] = None,
    program: Optional[str] = None,
    semester: Optional[str] = None
):
    user = request.state.user
    role = user.get("role")
    
    print(f"➡️ User Role: {role} is requesting subjects for Timetable with filters - Department: {department}, Program: {program}, Semester: {semester}")

    #auth
    if role != "clerk":
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "message": "You are not authorized to access subjects"
            }
        )

    match_stage = {}

    #convert comma-separated → list
    if program:
        program_list = [p.strip() for p in program.split(",") if p.strip()]
        match_stage["program"] = {"$in": program_list}

    if department:
        dept_list = [d.strip() for d in department.split(",") if d.strip()]
        match_stage["department"] = {"$in": dept_list}

    if semester:
        
        semester_list = [int(s.strip()) for s in semester.split(",") if s.strip()]
        match_stage["semester"] = {"$in": semester_list}
       

    pipeline = [
        {
            "$match": match_stage
        },

        {
            "$project": {
                "_id": {"$toString": "$_id"},
                "subject_name": 1,
                "subject_code": 1,
                "component": 1,
            }
        }
    ]

    result = await Subject.aggregate(pipeline).to_list()

    if not result:
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "No subjects found",
                "data": []
            }
        )

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "Subject details fetched successfully",
            "data": result,
        }
    )