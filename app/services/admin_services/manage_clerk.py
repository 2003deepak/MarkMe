from typing import Optional

from fastapi import HTTPException, Request, logger
from fastapi.responses import JSONResponse
from numpy import random
from app.core import redis
from app.core.redis import get_redis_client
import json
from app.models.allModel import ClerkFullView, ClerkShortView, CreateClerkRequest, UpdateAcademicScopesRequest
from app.schemas import clerk
from app.schemas.clerk import AcademicScope, AcademicScope, Clerk  
from bson import ObjectId
from datetime import datetime
from fastapi.encoders import jsonable_encoder
from app.utils.publisher import send_to_queue
from app.utils.redis_key_deletion import invalidate_redis_keys
from app.utils.security import get_password_hash
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# JSON encoder to handle ObjectId and datetime
class MongoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


async def edit_clerk(request: Request, clerk_id: str, body: UpdateAcademicScopesRequest):

    user_role = request.state.user.get("role")

    if user_role != "admin":
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "message": "Only Admin can access this route"
            }
        )

    # find clerk by id
    clerk = await Clerk.get(ObjectId(clerk_id))

    if not clerk:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "message": "Clerk not found"
            }
        )

    # convert scopes to dict (clean format)
    new_scopes = [
        {
            "program_id": scope.program_id,
            "department_id": scope.department_id
        }
        for scope in body.academic_scopes
    ]

    # remove duplicates (important)
    unique_scopes = {
        (s["program_id"], s["department_id"]): s
        for s in new_scopes
    }.values()

    # update clerk
    clerk.academic_scopes = list(unique_scopes)

    # save to DB
    await clerk.save()
    
    invalidate_redis_keys("clerks:profile:*")
    
    # send email notification
    try:
        scopes_text = "\n".join([
            f"- Program: {s.program_id} | Department: {s.department_id}"
            for s in clerk.academic_scopes
        ])

        await send_to_queue("email_queue", {
            "type": "send_email",
            "data": {
                "to": clerk.email,
                "subject": "Your Academic Access Has Been Updated",
                "body": (
                    f"Dear {clerk.first_name},\n\n"
                    f"Your academic access scopes have been successfully updated by the admin.\n\n"
                    f"You are now assigned to the following:\n\n"
                    f"{scopes_text}\n\n"
                    f"Please review your access and ensure everything is correct.\n\n"
                    f"If you notice any discrepancies, contact the admin team.\n\n"
                    f"Regards,\n"
                    f"MarkMe Team"
                )
            }
        }, priority=5)

    except Exception as e:
        logger.error(f"❌ Failed to send scope update email: {str(e)}")


    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "Academic scopes updated successfully"
        }
    )
    

async def create_clerk(request, request_model: CreateClerkRequest):

    if request.state.user.get("role") != "admin":
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "message": "You don't have right to create clerk"
            }
        )

    try:
        
        redis = await get_redis_client()
        existing_clerk = await Clerk.find_one(Clerk.email == request_model.email)

        if existing_clerk:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "message": "Clerk already exists"
                }
            )

        #generate pin
        pin = str(random.randint(100000, 999999))

        #hash pin
        hashed_pin = get_password_hash(pin)

        #build academic scopes
        scopes = [
            AcademicScope(
                program_id=s.program_id,
                department_id=s.department_id
            )
            for s in request_model.academic_scopes
        ]

        #create clerk
        clerk = Clerk(
            first_name=request_model.first_name,
            middle_name=request_model.middle_name,
            last_name=request_model.last_name,
            email=request_model.email,
            password=hashed_pin,
            phone=request_model.mobile_number,
            academic_scopes=scopes
        )

        await clerk.insert()
        
        await invalidate_redis_keys("clerks:*")

        #clear redis cache for all departments
        for scope in scopes:
            cache_key = f"clerks:{scope.department_id}"
            await redis.delete(cache_key)

        #send email task
        await send_to_queue(
            "email_queue",
            {
                "type": "send_email",
                "data": {
                    "to": request_model.email,
                    "subject": "Welcome to MarkMe!",
                    "body": f"Hello {request_model.first_name}, your registration is successful as Clerk. Your login PIN is <strong>{pin}</strong>."
                }
            },
            priority=5
        )

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Clerk created successfully",
                "data": {
                    "name": f"{request_model.first_name} {request_model.last_name}",
                    "email": request_model.email,
                    "academic_scopes": [
                        {
                            "program_id": s.program_id,
                            "department_id": s.department_id
                        }
                        for s in scopes
                    ]
                }
            }
        )

    except HTTPException:
        raise

    except Exception as e:
        print(f"Clerk creation error: {str(e)}")

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"Error creating clerk: {str(e)}"
            }
        )
        
        
async def get_clerk(
    request: Request,
    department: Optional[str] = None,
    program: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    limit: int = 10
):
    
    print(f"➡️ get_clerk called with department={department}, program={program}, search={search}, page={page}, limit={limit}")

    user = request.state.user
    role = user.get("role")
    
    redis = await get_redis_client()

    #auth
    if role != "admin":
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "message": "Only Admin can access this route",
            }
        )

    #validation
    page = max(page, 1)
    limit = max(min(limit, 100), 1)
    skip = (page - 1) * limit

    search_query = search.strip() if search else None

    #cache key (include everything)
    cache_key = f"clerks:{department or 'all'}:{program or 'all'}:{search_query or 'none'}:{page}:{limit}"

    cached_data = await redis.get(cache_key)
    if cached_data:
        print(f"✅ Cache hit: {cache_key}")
        return JSONResponse(
            status_code=200,
            content=json.loads(cached_data)
        )

    print("ℹ️ Cache miss — fetching from DB")

    #build query
    query = {}

    # academic scope filter
    if program or department:

        scope_filter = {}

        if program:
            scope_filter["program_id"] = program

        if department:
            scope_filter["department_id"] = department

        query["academic_scopes"] = {
            "$elemMatch": scope_filter
        }

    #search filter
    if search_query:
        regex = {"$regex": search_query, "$options": "i"}
        query["$or"] = [
            {"first_name": regex},
            {"last_name": regex},
            {"middle_name": regex},
            {"email": regex}
        ]

    #total count
    total = await Clerk.find(query).count()

    if total == 0:
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "No clerks found"
            }
        )

    #fetch data
    clerks = (
        await Clerk.find(query)
        .sort("first_name")
        .skip(skip)
        .limit(limit)
        .project(ClerkShortView)
        .to_list()
    )

    #pagination
    total_pages = (total + limit - 1) // limit

    response_payload = {
        "data": jsonable_encoder(
            [clerk.model_dump() for clerk in clerks],
            custom_encoder={
                ObjectId: str,
                datetime: lambda x: x.isoformat()
            }
        ),
        "count": len(clerks),
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1
    }

    final_response = {
        "success": True,
        "message": "Clerks fetched successfully",
        **response_payload
    }

    #store in redis
    await redis.setex(
        cache_key,
        86400,
        json.dumps(final_response)
    )

    print(f"📥 Saved to Redis: {cache_key}")

    return JSONResponse(
        status_code=200,
        content=final_response
    )
    
async def get_clerk_by_id(request: Request, clerk_id: str):

    user_role = request.state.user.get("role")

    if user_role != "admin":
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "message": "Only Admin can access this route"
            }
        )

    clerk = await Clerk.find_one(Clerk.id == ObjectId(clerk_id)).project(ClerkFullView)

    if not clerk:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "message": "Clerk not found"
            }
        )

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "Clerk Fetched Successfully",
            "data": clerk.model_dump(mode="json", by_alias=True)
        }
    )
    
