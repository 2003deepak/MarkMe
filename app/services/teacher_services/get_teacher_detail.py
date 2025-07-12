from fastapi import HTTPException
from app.core.database import get_db
from app.core.redis import redis_client
from bson import ObjectId
import json

# Helper class to encode ObjectId for JSON
class MongoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        return super().default(obj)


#  1. Get Teacher’s Own Profile
async def get_teacher_me(user_data: dict):
    
    if user_data["role"] != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can access this route")

    teacher_email = user_data["email"]
    cache_key = f"teacher:{teacher_email}"

    cached_data = await redis_client.get(cache_key)
    if cached_data:
        return {"status": "success", "data": json.loads(cached_data)}

    db = get_db()
    teacher = await db.teachers.find_one(
        {"email": teacher_email},
        {"password": 0, "created_at": 0, "updated_at": 0, "password_reset_otp": 0, "password_reset_otp_expires": 0}
    )

    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")

    teacher_json = json.loads(json.dumps(teacher, cls=MongoJSONEncoder))
    await redis_client.setex(cache_key, 3600, json.dumps(teacher_json))  # Cache for 1 hour

    return {"status": "success", "data": teacher_json}


#  2. Get Teacher Details by ID (used by Clerk)
async def get_teacher_by_id(teacher_id: str, user_data: dict):
    if user_data["role"] != "clerk":
        raise HTTPException(status_code=403, detail="Only clerks can access this route")

    cache_key = f"teacher:{teacher_id}"
    cached_teacher = await redis_client.get(cache_key)

    if cached_teacher:
        return {"status": "success", "data": json.loads(cached_teacher)}

    db = get_db()
    teacher = await db.teachers.find_one(
        {"teacher_id": teacher_id},
        {"password": 0, "created_at": 0, "updated_at": 0, "password_reset_otp": 0, "password_reset_otp_expires": 0}
    )

    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")

    teacher_json = json.loads(json.dumps(teacher, cls=MongoJSONEncoder))
    await redis_client.setex(cache_key, 3600, json.dumps(teacher_json))  # Cache for 1 hour

    return {"status": "success", "data": teacher_json}
