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


async def get_clerk(department: str, user_data: dict):

    print(f"🧾 user_data = {user_data}")  # 🔍 Inspect structure
    
    user_email = user_data["email"]
    user_role = user_data["role"]
    department = department.upper()

    print(f"➡️ Requested by: {user_email} (Role: {user_role}, Department: {department})")

    if user_role != "admin":
        print("❌ Access denied: Not an Admin")
        raise HTTPException(
            status_code=403,
            detail={"status": "fail", "message": "Only Admin can access this route"}
        )
    
    # Improved Redis key naming
    cache_key = f"clerk:{department}"
    cached_clerk = await redis_client.get(cache_key)
    
    if cached_clerk:
        print("✅ Found data in Redis cache")
        clerk_data = json.loads(cached_clerk)
        if "clerks" in clerk_data:
            print(f"📦 Returning cached clerks for {cache_key}")
            return {"status": "success", "data": clerk_data}

    print("ℹ️ No cached data found — fetching from DB...")

    # Filter out unwanted fields from clerk
    exclude_fields = {
        "password": 0,
        "created_at": 0,
        "updated_at": 0,
        "password_reset_otp": 0,
        "password_reset_otp_expires": 0,
    }
    clerks_collection = get_db().clerks
    cursor = clerks_collection.find({"department": department}, exclude_fields)
    clerks = await cursor.to_list(length=None)
    
    if not clerks:
        print("❌ No clerks found in DB")
        raise HTTPException(
            status_code=404,
            detail={"status": "fail", "message": f"Clerk not found in department {department}"}
        )
        
    # Wrap in dict before saving to Redis
    clerk_data = {
        "department": department,
        "clerks": clerks
    }

    # Serialize with MongoJSONEncoder for Redis
    serialized_clerk_data = json.dumps(clerk_data, cls=MongoJSONEncoder)
    await redis_client.set(cache_key, serialized_clerk_data, ex=86400)
    print(f"📥 Saved clerks for {department} to Redis (TTL 24h)")

    # Use jsonable_encoder to ensure proper serialization for response
    return {"status": "success", "data": jsonable_encoder(clerk_data, custom_encoder={ObjectId: str, datetime: lambda x: x.isoformat()})}

async def get_clerk_by_id(email_id: str, user_data: dict):

    print(f"🧾 user_data = {user_data}, Clerk id = {email_id}")  # 🔍 Inspect structure
    email_id = email_id.lower()
    user_email = user_data["email"]
    user_role = user_data["role"]
    
    if user_role != "admin":
        print("❌ Access denied: Not an Admin")
        raise HTTPException(
            status_code=403,
            detail={"status": "fail", "message": "Only Admin can access this route"}
        )
    
    # Improved Redis key naming
    cache_key = f"clerk:{email_id}"
    cached_clerk = await redis_client.get(cache_key)
    
    if cached_clerk:
        print(f"✅ Found cached clerk for {cache_key}")
        return {"status": "success", "data": json.loads(cached_clerk)}

    exclude_fields = {
        "password": 0,
        "created_at": 0,
        "updated_at": 0,
        "password_reset_otp": 0,
        "password_reset_otp_expires": 0,
    }
    
    clerks_collection = get_db().clerks
    clerk = await clerks_collection.find_one({"email": email_id}, exclude_fields)
    
    if not clerk:
        raise HTTPException(status_code=404, detail=f"Clerk not found ")

    # Serialize with MongoJSONEncoder for Redis
    clerk_json = json.dumps(clerk, cls=MongoJSONEncoder)
    await redis_client.setex(cache_key, 3600, clerk_json)  # Cache for 1 hour
    print(f"📥 Saved clerk {email_id} to Redis (TTL 1h)")

    # Use jsonable_encoder to ensure proper serialization for response
    return {"status": "success", "data": jsonable_encoder(clerk, custom_encoder={ObjectId: str, datetime: lambda x: x.isoformat()})}