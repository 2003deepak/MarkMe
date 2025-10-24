from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from app.core.redis import redis_client
import json
from app.core.database import get_db
from app.schemas.clerk import Clerk
from datetime import datetime
from fastapi.encoders import jsonable_encoder
from bson import ObjectId
from typing import Optional
from app.models.allModel import ClerkShortView

# JSON encoder to handle ObjectId and datetime
class MongoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)



async def get_clerk(request : Request , department: str):
    
    user_email = request.state.user.get("email")
    user_role = request.state.user.get("role")
    department = department.upper()

    print(f"➡️ Requested by: {user_email} (Role: {user_role}, Department: {department})")

    if user_role != "admin":

        return JSONResponse(
        status_code=403,
        content={
            "success": False,
            "message": "Only Admin can access this route",
            
        }
    )
    
    # Improved Redis key naming
    cache_key = f"clerks:{department}"
    cached_clerk = await redis_client.get(cache_key)
    
    if cached_clerk:
        print("✅ Found data in Redis cache")
        clerk_data = json.loads(cached_clerk)
        if "clerks" in clerk_data:
            print(f"📦 Returning cached clerks for {cache_key}")
            return {"status": "success", "data": clerk_data}

    print("ℹ️ No cached data found — fetching from DB...")

    # Use Beanie's project method with ClerkShortView
    clerks = await Clerk.find(Clerk.department == department).project(ClerkShortView).to_list()
    
    if not clerks:
        print("❌ No clerks found in DB")

        return JSONResponse(
        status_code=404,
        content={
            "success": False,
            "message": f"Clerk not found in department {department}",
            
        })
        
        
        
    # Wrap in dict before saving to Redis
    clerk_data = {
        "department": department,
        "clerks": [clerk.dict() for clerk in clerks]
    }

    # Serialize with MongoJSONEncoder for Redis
    serialized_clerk_data = json.dumps(clerk_data, cls=MongoJSONEncoder)
    await redis_client.set(cache_key, serialized_clerk_data, ex=86400)
    print(f"📥 Saved clerks for {department} to Redis (TTL 24h)")

    # Use jsonable_encoder to ensure proper serialization for response

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "Clerk fetched successfully",
            "data": jsonable_encoder(
                clerk_data,
                custom_encoder={ObjectId: str, datetime: lambda x: x.isoformat()}
            )
            
        })

async def get_clerk_by_id(request : Request ,email_id: str):
    
    user_email = request.state.user.get("email")
    user_role = request.state.user.get("role")
    
    if user_role != "admin":
        print("❌ Access denied: Not an Admin")
        
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "message": "Only Admin can access this route"
            }
        )
    
    # Improved Redis key naming
    cache_key = f"clerk:{email_id}"
    cached_clerk = await redis_client.get(cache_key)
    
    if cached_clerk:
        print(f"✅ Found cached clerk for {cache_key}")
        return {"status": "success", "data": json.loads(cached_clerk)}

    # Fetch clerk by email using project method
    clerk = await Clerk.find_one(Clerk.email == email_id).project(ClerkShortView)
    
    if not clerk:
        print(f"❌ Clerk {email_id} not found in DB")

        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "message": "Clerk not found"
            }
        )

    # Convert to dict for Redis
    clerk_dict = clerk.dict()

    # Serialize with MongoJSONEncoder for Redis
    clerk_json = json.dumps(clerk_dict, cls=MongoJSONEncoder)
    await redis_client.setex(cache_key, 3600, clerk_json)  # Cache for 1 hour
    print(f"📥 Saved clerk {email_id} to Redis (TTL 1h)")

    
    return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Clerk Fetched Successfully",
                "data": jsonable_encoder(
                        clerk_dict,
                        custom_encoder={ObjectId: str, datetime: lambda x: x.isoformat()}
                    )
            }
        )