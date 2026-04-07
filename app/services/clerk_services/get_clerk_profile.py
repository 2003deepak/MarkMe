from fastapi import Request
from fastapi.responses import JSONResponse
from app.schemas.clerk import Clerk
from app.core.redis import get_redis_client
import json


async def get_clerk_profile(request: Request):
    redis = await get_redis_client()

    try:

        user = request.state.user
        user_email = user.get("email")
        user_role = user.get("role")

        if not user_email:
            return JSONResponse(
                status_code=401,
                content={
                    "success": False,
                    "message": "User email not found in request"
                }
            )

        if user_role != "clerk":
            return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "message": "Only clerks can access this endpoint"
                }
            )

        #redis cache
        cache_key = f"clerk:profile:{user_email}"

        cached_data = await redis.get(cache_key)

        if cached_data:
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "message": "Clerk profile fetched successfully",
                    "data": json.loads(cached_data)
                }
            )

        #fetch clerk
        clerk = await Clerk.find_one(Clerk.email == user_email)

        if not clerk:
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "message": "Clerk profile not found"
                }
            )

        #format academic scopes
        scopes = []

        if clerk.academic_scopes:
            for scope in clerk.academic_scopes:
                scopes.append({
                    "program_id": scope.program_id,
                    "department_id": scope.department_id
                })

        clerk_data = {
            "clerk_id": str(clerk.id),
            "first_name": clerk.first_name,
            "middle_name": clerk.middle_name,
            "last_name": clerk.last_name,
            "email": clerk.email,
            "phone": clerk.phone,
            "profile_picture": clerk.profile_picture,
            "profile_picture_id": clerk.profile_picture_id,
            "academic_scopes": scopes,
            "created_at": clerk.created_at.isoformat() if clerk.created_at else None,
            "updated_at": clerk.updated_at.isoformat() if clerk.updated_at else None
        }

        #save cache
        await redis.setex(
            cache_key,
            3600,
            json.dumps(clerk_data)
        )

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Clerk profile fetched successfully",
                "data": clerk_data
            }
        )

    except Exception as e:

        print(f"Clerk profile error: {str(e)}")

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "Internal server error while fetching profile"
            }
        )