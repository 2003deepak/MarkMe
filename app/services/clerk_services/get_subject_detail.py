from fastapi import HTTPException
from app.core.redis import redis_client
import json
from app.core.database import get_db
from app.schemas.clerk import Clerk
from app.schemas.subject import Subject
from bson import ObjectId
from datetime import datetime
from fastapi.encoders import jsonable_encoder
from app.models.allModel import SubjectShortView

# JSON encoder to handle ObjectId and datetime
class MongoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

async def get_subject_detail(user_data: dict):
    print(f"🧾 user_data = {user_data}")
    user_email = user_data["email"]
    user_role = user_data["role"]
    
    if user_role != "clerk":
        print("❌ Access denied: Not a clerk")
        raise HTTPException(
            status_code=403,
            detail={"status": "fail", "message": "Only Clerk can access this route"}
        )
    
    clerk_program = user_data["program"]
    print(f"➡️ Requested by: {user_email} (Role: {user_role}, Program: {clerk_program})")
    
    # Simplified Redis key naming
    cache_key = f"subject:{clerk_program}"
    cached_subject = await redis_client.get(cache_key)

    if cached_subject:
        print(f"✅ Found data in Redis cache: {cache_key}")
        subject_data = json.loads(cached_subject)
        if "subjects" in subject_data:
            print(f"📦 Returning cached subjects for {cache_key}")
            return {"status": "success", "data": subject_data}

    print("ℹ️ No cached data found — fetching from DB...")

    # Fetch subjects by department and resolve teacher_assigned references
    subjects = await Subject.find(
        Subject.program == clerk_program,
        fetch_links=True  # Fetch linked teacher data
    ).project(SubjectShortView).to_list() 

    if not subjects:
        print("❌ No subjects found in DB")
        return {"status": "success", "data": "No subjects found"}

    # Wrap in dict before saving to Redis
    subject_data = {
        "program": clerk_program,
        "subjects": [subject.dict() for subject in subjects]
    }

    # Save to Redis with 24hr TTL
    serialized_subject_data = json.dumps(subject_data, cls=MongoJSONEncoder)
    await redis_client.set(cache_key, serialized_subject_data, ex=86400)
    print(f"📥 Saved subjects for {clerk_program} to Redis (TTL 24h)")

    # Use jsonable_encoder for response
    return {"status": "success", "data": jsonable_encoder(subject_data, custom_encoder={ObjectId: str, datetime: lambda x: x.isoformat()})}



async def get_subject_by_id(subject_id: str, user_data: dict):
    print(f"🧾 user_data = {user_data}, Subject id = {subject_id}")
    subject_id = subject_id.upper()
    user_email = user_data["email"]
    user_role = user_data["role"]

    if user_role != "clerk":
        print("❌ Access denied: Not a clerk")
        raise HTTPException(
            status_code=403,
            detail={"status": "fail", "message": "Only Clerk can access this route"}
        )

    clerk_program = user_data["program"]
    print(f"➡️ Requested by: {user_email} (Role: {user_role}, Program: {clerk_program})")

    # Simplified Redis key naming
    cache_key = f"subject:{subject_id}:{clerk_program}"
    cached_subject = await redis_client.get(cache_key)

    if cached_subject:
        print(f"✅ Found data in Redis cache: {cache_key}")
        return {"status": "success", "data": json.loads(cached_subject)}

    print("ℹ️ No cached data found — fetching from DB...")

    # Query all subjects by subject_code and program, and fetch linked teacher data
    subjects = await Subject.find(
        Subject.subject_code == subject_id,
        Subject.program == clerk_program,
        fetch_links=True  
    ).project(SubjectShortView).to_list()

    if not subjects:
        print(f"❌ Subjects not found: {subject_id} in Program {clerk_program}")
        raise HTTPException(
            status_code=404,
            detail={"status": "fail", "message": f"No subjects found with ID {subject_id} in Program {clerk_program}"}
        )

    # Wrap in dict for response and Redis
    subject_data = {
        "program": clerk_program,
        "subject_code": subject_id,
        "subjects": [subject.dict() for subject in subjects]
    }

    # Save to Redis with 24hr TTL
    serialized_subject = json.dumps(subject_data, cls=MongoJSONEncoder)
    await redis_client.set(cache_key, serialized_subject, ex=86400)
    print(f"📥 Saved subjects {subject_id} for {clerk_program} to Redis (TTL 24h)")

    # Use jsonable_encoder for response
    return {"status": "success", "data": jsonable_encoder(subject_data, custom_encoder={ObjectId: str, datetime: lambda x: x.isoformat()})}