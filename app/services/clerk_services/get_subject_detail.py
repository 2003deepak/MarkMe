from fastapi import HTTPException
from app.core.redis import redis_client
import json
from app.core.database import get_db
from bson import ObjectId
from datetime import datetime
from fastapi.encoders import jsonable_encoder

# JSON encoder to handle ObjectId and datetime
class MongoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

async def get_subject_detail(user_data: dict):

    print(f"🧾 user_data = {user_data}")  # 🔍 Inspect structure
    user_email = user_data["email"]
    user_role = user_data["role"]
    
    if user_role != "clerk":
        print("❌ Access denied: Not a clerk")
        raise HTTPException(
            status_code=403,
            detail={"status": "fail", "message": "Only Clerk can access this route"}
        )
    
    # Filter out unwanted fields from clerk
    exclude_fields = {
        "password": 0,
        "created_at": 0,
        "updated_at": 0,
        "password_reset_otp": 0,
        "password_reset_otp_expires": 0,
    }
    
    clerks_collection = get_db().clerks
    clerk = await clerks_collection.find_one({"email": user_email}, exclude_fields)
    
    if not clerk:
        print(f"❌ Clerk not found for email: {user_email}")
        raise HTTPException(
            status_code=404,
            detail={"status": "fail", "message": "Clerk not found"}
        )
    
    clerk_department = clerk.get("department")
    print(f"➡️ Requested by: {user_email} (Role: {user_role}, Department: {clerk_department})")
    
    # Simplified Redis key naming
    cache_key = f"subjects:{clerk_department.lower()}"
    cached_subject = await redis_client.get(cache_key)

    if cached_subject:
        print(f"✅ Found data in Redis cache: {cache_key}")
        subject_data = json.loads(cached_subject)
        if "subjects" in subject_data:
            print(f"📦 Returning cached subjects for {cache_key}")
            return {"status": "success", "data": subject_data}

    print("ℹ️ No cached data found — fetching from DB...")

    # Filter out unwanted fields from subjects
    exclude_fields = {
        "created_at": 0,
        "updated_at": 0,
    }

    subjects_collection = get_db().subjects
    cursor = subjects_collection.find({"department": clerk_department}, exclude_fields)
    subjects = await cursor.to_list(length=None)

    if not subjects:
        print("❌ No subjects found in DB")
        raise HTTPException(
            status_code=404,
            detail={"status": "fail", "message": f"No subjects found for department {clerk_department}"}
        )

    # Wrap in dict before saving to Redis
    subject_data = {
        "department": clerk_department,
        "subjects": subjects
    }

    # Save to Redis with 24hr TTL
    serialized_subject_data = json.dumps(subject_data, cls=MongoJSONEncoder)
    await redis_client.set(cache_key, serialized_subject_data, ex=86400)
    print(f"📥 Saved subjects for {clerk_department} to Redis (TTL 24h)")

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

    # Fetch clerk to get department
    exclude_fields = {
        "password": 0,
        "created_at": 0,
        "updated_at": 0,
        "password_reset_otp": 0,
        "password_reset_otp_expires": 0,
    }

    clerks_collection = get_db().clerks
    clerk = await clerks_collection.find_one({"email": user_email}, exclude_fields)
    
    if not clerk:
        print(f"❌ Clerk not found for email: {user_email}")
        raise HTTPException(
            status_code=404,
            detail={"status": "fail", "message": "Clerk not found"}
        )

    clerk_department = clerk.get("department")
    print(f"➡️ Requested by: {user_email} (Role: {user_role}, Department: {clerk_department})")

    # Simplified Redis key naming
    cache_key = f"subject:{subject_id}"
    cached_subject = await redis_client.get(cache_key)

    if cached_subject:
        print(f"✅ Found data in Redis cache: {cache_key}")
        return {"status": "success", "data": json.loads(cached_subject)}

    print("ℹ️ No cached data found — fetching from DB...")

    # Query subject directly by subject_code and department
    subjects_collection = get_db().subjects
    subject = await subjects_collection.find_one(
        {"subject_code": subject_id, "department": clerk_department},
        {"created_at": 0, "updated_at": 0}
    )

    if not subject:
        print(f"❌ Subject not found: {subject_id} in department {clerk_department}")
        raise HTTPException(
            status_code=404,
            detail={"status": "fail", "message": f"Subject with ID {subject_id} not found in department {clerk_department}"}
        )

    # Save to Redis with 24hr TTL
    serialized_subject = json.dumps(subject, cls=MongoJSONEncoder)
    await redis_client.set(cache_key, serialized_subject, ex=86400)
    print(f"📥 Saved subject {subject_id} for {clerk_department} to Redis (TTL 24h)")

    # Use jsonable_encoder for response
    return {"status": "success", "data": jsonable_encoder(subject, custom_encoder={ObjectId: str, datetime: lambda x: x.isoformat()})}