from fastapi import HTTPException
from app.core.redis import redis_client
import json
from app.core.database import get_db
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


async def get_subject_detail(user_data):
    print("🧾 user_data =", user_data)  # 🔍 Inspect structure
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
    clerk_department = clerk.get('department')
    print(f"➡️ Requested by: {user_email} (Role: {user_role} Department {clerk_department}")
    
    

    cache_key_clerk = f"{user_role}:{clerk_department}"
    cached_subject = await redis_client.get(cache_key_clerk)

    if cached_subject:
        print("✅ Found data in Redis cache")
        subject_data = json.loads(cached_subject)
        if "subjects" in subject_data:
            print(f"📦 Returning cached subjects for {cache_key_clerk}")
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
            detail={"status": "fail", "message": "Subjects not found"}
        )

 

    # Wrap in dict before saving to Redis
    subject_data = {
        "department": clerk_department,
        "subjects": subjects
    }

    # Save to Redis with 24hr TTL
    await redis_client.set(cache_key_clerk, json.dumps(subject_data,cls=MongoJSONEncoder), ex=86400)
    print(f"📥 Saved subjects for {clerk_department} to Redis (TTL 24h)")

    return {"status": "success", "data": subject_data}
        
        
        
async def get_subject_by_id(subject_id, user_data):
    print("🧾 user_data =", user_data,"Subject id ",subject_id)  # 🔍 Inspect structure
    user_email = user_data["email"]
    user_role = user_data["role"]
    
    if user_role != "clerk":
        print("❌ Access denied: Not a clerk")
        raise HTTPException(
            status_code=403,
            detail={"status": "fail", "message": "Only Clerk can access this route"}
        )
        
    exclude_fields = {
        "password": 0,
        "created_at": 0,
        "updated_at": 0,
        "password_reset_otp": 0,
        "password_reset_otp_expires": 0,
    }
    
    clerks_collection = get_db().clerks
    clerk = await clerks_collection.find_one({"email": user_email}, exclude_fields)
    clerk_department = clerk.get('department')
    print(f"➡️ Requested by: {user_email} (Role: {user_role} Department {clerk_department}")
    
    
    cache_key_clerk = f"{user_role}:{clerk_department}"
    cached_subject = await redis_client.get(cache_key_clerk)

    if cached_subject:
        print("✅ Found data in Redis cache")
        subject_data = json.loads(cached_subject)
        if "subjects" in subject_data:
            # 🔍 Iterate through cached subjects and find match
            for subject in subject_data["subjects"]:
                if subject.get("subject_code") == subject_id:
                    print(f"🎯 Found matching subject: {subject}")
                    return {"status": "success", "data": subject}
            print(f"📦 Returning cached subjects for {cache_key_clerk}")
            

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
            detail={"status": "fail", "message": "Subjects not found"}
        )


    # Wrap in dict before saving to Redis
    subject_data = {
        "department": clerk_department,
        "subjects": subjects
    }

    # Save to Redis with 24hr TTL
    await redis_client.set(cache_key_clerk, json.dumps(subject_data,cls=MongoJSONEncoder), ex=86400)
    print(f"📥 Saved subjects for {clerk_department} to Redis (TTL 24h)")

    for subject in subjects:
        if subject.get("subject_code") == subject_id:
            print(f"🎯 Found matching subject: {subject}")
            return {"status": "success", "data": subject}
        else:
            raise HTTPException(
            status_code=404,
            detail={"status": "fail", "message": "Subject with not found"}
        )
