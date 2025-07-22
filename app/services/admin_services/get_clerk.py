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



async def get_clerk(department, user_data):
    print("🧾 user_data =", user_data)  # 🔍 Inspect structure
    
    user_email = user_data["email"]
    user_role = user_data["role"]
    department = department.upper()

    print(f"➡️ Requested by: {user_email} (Role: {user_role} Department {department}")

    
    if user_role != "admin":
        print("❌ Access denied: Not a Admin")
        raise HTTPException(
            status_code=403,
            detail={"status": "fail", "message": "Only Admin can access this route"}
        )
    
    cache_key_clerk = f"{user_role}:clerk:{department}"
    cached_clerk = await redis_client.get(cache_key_clerk)
    
    if cached_clerk:
        print("✅ Found data in Redis cache")
        clerk_data = json.loads(cached_clerk)
        if "clerks" in clerk_data:
            print(f"📦 Returning cached Clerk for {cache_key_clerk}")
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
    cursor =  clerks_collection.find({"department": department}, exclude_fields)
    clerks = await cursor.to_list(length=None)
    

    if not clerks:
        print("❌ No Clerks found in DB")
        raise HTTPException(
            status_code=404,
            detail={"status": "fail", "message": f"Clerk not found in department {department}"}
        )
        
    # Wrap in dict before saving to Redis
    clerk_data = {
        "department": department,
        "clerks": clerks
    }
    # Save to Redis with 24hr TTL
    await redis_client.set(cache_key_clerk, json.dumps(clerk_data, cls=MongoJSONEncoder), ex=86400)
    print(f"📥 Saved Clerks for {department} to Redis (TTL 24h)")

    return {"status": "success", "data": clerk_data}
    
    
async def get_clerk_by_id(clerk_id, user_data):
    print("🧾 user_data =", user_data,"Clerk id ",clerk_id)  # 🔍 Inspect structure
    clerk_id = clerk_id.lower()
    user_email = user_data["email"]
    user_role = user_data["role"]
    
    if user_role != "admin":
        print("❌ Access denied: Not a Admin")
        raise HTTPException(
            status_code=403,
            detail={"status": "fail", "message": "Only Admin can access this route"}
        )
    exclude_fields = {
        "password": 0,
        "created_at": 0,
        "updated_at": 0,
        "password_reset_otp": 0,
        "password_reset_otp_expires": 0,
    }
    
    cache_key_clerk = f"{user_role}:clerk:{clerk_id}"
    cached_clerk = await redis_client.get(cache_key_clerk)
    
    if cached_clerk:
        return {"status": "success", "data": json.loads(cached_clerk)}

    
    clerks_collection = get_db().clerks
    clerk = await clerks_collection.find_one({"email": clerk_id}, exclude_fields)
    
    if not clerk:
        raise HTTPException(status_code=404, detail=f"Clerk not found with id {clerk_id}")

    clerk_json = json.loads(json.dumps(clerk, cls=MongoJSONEncoder))
    await redis_client.setex(cache_key_clerk, 3600, json.dumps(clerk_json))  # Cache for 1 hour

    return {"status": "success", "data": clerk_json}