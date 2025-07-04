from fastapi import HTTPException
from app.core.database import get_db
from app.core.redis import redis_client
import json
from bson import ObjectId
from datetime import datetime

# JSON encoder to handle ObjectId and datetime
class MongoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

async def get_student_detail(user_data):

    user_email = user_data["email"]
    user_role = user_data["role"]

    if user_role != "student":
        raise HTTPException(
            status_code=403,
            detail={"status": "fail", "message": "Only students can access this route"}
        )

    cache_key_student = f"student:{user_email}"
    cached_student = await redis_client.get(cache_key_student)

    if cached_student:
        student_data = json.loads(cached_student)
        # Check if subjects are already included in cached student data
        if "subjects" in student_data:
            return {"status": "success", "data": student_data}

    # Filter out unwanted fields from student
    exclude_fields = {
        "password": 0,
        "created_at": 0,
        "updated_at": 0,
        "password_reset_otp": 0,
        "password_reset_otp_expires": 0,
        "face_embedding": 0,
    }

    students_collection = get_db().students
    student = await students_collection.find_one({"email": user_email}, exclude_fields)

    if not student:
        raise HTTPException(
            status_code=404,
            detail={"status": "fail", "message": "Student not found"}
        )

    # Get program, department, and semester from student data
    program = student.get("program")
    department = student.get("department")
    semester = student.get("semester")

    if not all([program, department, semester]):
        raise HTTPException(
            status_code=400,
            detail={"status": "fail", "message": "Student missing program, department, or semester"}
        )

    # Create cache key for subjects
    cache_key_subjects = f"subjects:{program}:{department}:{semester}"
    cached_subjects = await redis_client.get(cache_key_subjects)

    subjects_data = None
    if cached_subjects:
        subjects_data = json.loads(cached_subjects)
    else:
        # Query subjects collection for all matching documents
        subjects_collection = get_db().subjects
        subjects_cursor = subjects_collection.find(
            {"program": program, "department": department, "semester": semester},
            {"_id": 0, "subject_code": 1, "subject_name": 1, "type": 1, "credit": 1, "teacher_assigned": 1}
        )

        subjects_data = []
        async for subject in subjects_cursor:
            subjects_data.append(subject)

        if not subjects_data:
            raise HTTPException(
                status_code=404,
                detail={"status": "fail", "message": "Subjects not found for the given program, department, and semester"}
            )

        # Cache subjects data for 24 hours
        await redis_client.setex(
            cache_key_subjects,
            86400,  # 24 hours
            json.dumps(subjects_data, cls=MongoJSONEncoder)
        )

    # Convert student data to JSON-compatible format
    student_json = json.loads(json.dumps(student, cls=MongoJSONEncoder))
    
    # Combine student data and subjects
    student_json["subjects"] = subjects_data

    # Cache the combined student data (including subjects) for 1 hour
    await redis_client.setex(
        cache_key_student,
        3600,  # 1 hour
        json.dumps(student_json, cls=MongoJSONEncoder)
    )

    return {"status": "success", "data": student_json}