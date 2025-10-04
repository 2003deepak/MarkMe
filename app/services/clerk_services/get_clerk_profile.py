from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from app.schemas.clerk import Clerk
from app.core.redis import redis_client
import json

async def get_clerk_profile(request: Request):
    try:
        # Get user email from request state
        user_email = request.state.user.get("email")
        user_role = request.state.user.get("role")
        
        if not user_email:
            return JSONResponse(
                status_code=401,
                content={
                    "status": "fail",
                    "message": "User email not found in request"
                }
            )
        
        if user_role != "clerk":
            return JSONResponse(
                status_code=403,
                content={
                    "status": "fail",
                    "message": "Only clerks can access this endpoint"
                }
            )

        # Check cache first
        cache_key = f"clerk:{user_email}"
        cached_data = await redis_client.get(cache_key)
        
        if cached_data:
            print(f"✅ Found clerk profile in cache: {cache_key}")
            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "data": json.loads(cached_data)
                }
            )

        print(f"ℹ️ No cached data found — fetching from DB for {user_email}...")
        
        # Fetch clerk from database
        clerk = await Clerk.find_one(Clerk.email == user_email)
        
        if not clerk:
            return JSONResponse(
                status_code=404,
                content={
                    "status": "fail",
                    "message": "Clerk profile not found"
                }
            )

        # Prepare response data
        clerk_data = {
            "clerk_id": str(clerk.id),
            "first_name": clerk.first_name,
            "middle_name": clerk.middle_name,
            "last_name": clerk.last_name,
            "email": clerk.email,
            "phone": clerk.phone,
            "department": clerk.department,
            "program": clerk.program,
            "profile_picture": clerk.profile_picture,
            "profile_picture_id": clerk.profile_picture_id,
            "created_at": clerk.created_at.isoformat() if clerk.created_at else None,
            "updated_at": clerk.updated_at.isoformat() if clerk.updated_at else None
        }

        # Cache the data for 1 hour
        await redis_client.setex(
            cache_key,
            3600,
            json.dumps(clerk_data)
        )
        print(f"📥 Saved clerk profile for {user_email} to Redis (TTL 1h)")

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "data": clerk_data
            }
        )

    except Exception as e:
        print(f"❌ Error fetching clerk profile: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "fail",
                "message": "Internal server error while fetching profile"
            }
        )