from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from app.core.database import get_db
from app.core.redis import redis_client
from bson import ObjectId
import json
from datetime import datetime
from pydantic import HttpUrl
from app.schemas.teacher import Teacher
from app.models.allModel import TeacherShortView


class MongoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, HttpUrl):  # Handle HttpUrl
            return str(obj)  # Convert HttpUrl to string
        return super().default(obj)

async def get_teacher_me(request: Request):
    user_role = request.state.user.get("role")
    if user_role != "teacher":
        return JSONResponse(
            status_code=403,
            content={
                "success": False, 
                "message": "Only teachers can access this route"
            }
        )

    teacher_email = request.state.user.get("email")
    cache_key = f"teacher:{teacher_email}"

    cached_data = await redis_client.get(cache_key)
    if cached_data:
        print(f"✅ Found data in Redis cache: {cache_key}")
        return JSONResponse(
            status_code=200,
            content={
                "success": True, 
                "message" : "Teacher details fetched successfully",
                "data": json.loads(cached_data)
            }
        )

    print(f"ℹ️ No cached data found — fetching from DB for {teacher_email}...")
    
    teacher = await Teacher.find_one(
        Teacher.email == teacher_email, 
        fetch_links=True
    ).project(TeacherShortView)

    if not teacher:
        print(f"❌ Teacher not found: {teacher_email}")
        return JSONResponse(
            status_code=404,
            content={
                "success": False, 
                "message": "Teacher not found"
            }
        )

    # Convert to dict and serialize with custom encoder
    teacher_dict = teacher.dict()
    teacher_json = json.dumps(teacher_dict, cls=MongoJSONEncoder)
    
    # Cache for 1 hour (3600 seconds)
    await redis_client.setex(cache_key, 3600, teacher_json)
    print(f"📥 Saved teacher {teacher_email} to Redis (TTL 1h)")

    # Return response 
    return JSONResponse(
        status_code=200,
        content={
            "success": True, 
            "message" : "Teacher details fetched successfully",
            "data": json.loads(teacher_json)
        }
    )


# 2. Get Teacher Details by ID (used by Clerk)
async def get_teacher_by_id(request: Request,teacher_id: str):
    user_role = request.state.user.get("role")
    if user_role != "clerk":
        return JSONResponse(
            status_code=403,
            content={
                "success": False, 
                "message": "Only clerks can access this route"
            }
        )

    # Cache check
    cache_key = f"teacher:{teacher_id}"
    cached_teacher = await redis_client.get(cache_key)
    if cached_teacher:
        return JSONResponse(
            status_code=200,
            content={
                "success": True, 
                "message" : "Teacher details fetched successfully",
                "data": json.loads(cached_teacher)
            }
        )

    # Fetch teacher doc
    teacher = await Teacher.find_one(Teacher.teacher_id == teacher_id)
    if not teacher:
        return JSONResponse(
            status_code=404,
            content={
                "success": False, 
                "message": "Teacher not found"
            }
        )

    # Fetch subject links
    await teacher.fetch_all_links()
    
    # Compose dict for Pydantic output
    teacher_dict = {
        "teacher_id": teacher.teacher_id,
        "first_name": teacher.first_name,
        "middle_name": teacher.middle_name,
        "last_name": teacher.last_name,
        "email": teacher.email,
        "mobile_number": teacher.mobile_number,
        "department": teacher.department,
        "profile_picture": teacher.profile_picture,
        "profile_picture_id": teacher.profile_picture_id,
        "subjects_assigned": [
            {"subject_code": subj.subject_code, "subject_name": subj.subject_name, "component": subj.component}
            for subj in teacher.subjects_assigned
        ],
    }
    # Validate output
    teacher_out_data = TeacherShortView.model_validate(teacher_dict)
    teacher_dict_for_response = teacher_out_data.model_dump(
        exclude_none=True,
        mode="json"
    )
    teacher_json = json.dumps(teacher_dict_for_response)
    await redis_client.setex(cache_key, 3600, teacher_json)
    
    return JSONResponse(
        status_code=200,
        content={
            "success": True, 
            "message" : "Teacher details fetched successfully",
            "data": teacher_dict_for_response
        }
    )