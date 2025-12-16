from typing import Literal, Optional
from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from bson import ObjectId
from datetime import datetime
import json

from app.core.redis import redis_client
from app.schemas.subject import Subject
from app.models.allModel import SubjectListingView, SubjectShortView


# Custom JSON encoder for Mongo-specific types
class MongoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)



async def get_subject_detail(
    request: Request,
    program: Optional[str] = None,
    semester: Optional[int] = None,
    mode: Literal["subject_listing", "subject_teacher_listing"] = "subject_teacher_listing",
):
    user = request.state.user
    user_role = user.get("role")
    department = user.get("department")

    # Role validation
    if user_role not in {"clerk", "student"}:
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "message": "You are not authorized to access subjects"
            }
        )

    # Cache key (mode-aware ❗)
    cache_key = f"subjects:{department}:{program}:{semester}:{mode}"
    cached = await redis_client.get(cache_key)

    if cached:
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Subject details fetched successfully",
                "data": json.loads(cached)
            }
        )

    # Build query dynamically
    query = {Subject.department: department}

    if program:
        query[Subject.program] = program
    if semester:
        query[Subject.semester] = semester

    projection = (
        SubjectListingView
        if mode == "subject_listing"
        else SubjectShortView
    )

    # Fetch from DB
    subjects = await Subject.find(
        *[k == v for k, v in query.items()],
        fetch_links=True
    ).project(projection).to_list()

    if not subjects:
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "No subjects found",
                "data" : []
            }
        )

    # Prepare response data
    response_data =  [s.dict() for s in subjects]

    # Cache result (24h)
    await redis_client.set(
        cache_key,
        json.dumps(response_data, cls=MongoJSONEncoder),
        ex=86400
    )

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "Subject details fetched successfully",
            "data": jsonable_encoder(
                response_data,
                custom_encoder={
                    ObjectId: str,
                    datetime: lambda x: x.isoformat()
                }
            )
        }
    )



async def get_subject_by_id(request : Request , subject_id: str):
    
    subject_id = subject_id.upper()
    user_email = request.state.user.get("email")
    user_role = request.state.user.get("role")

    if user_role != "clerk":
        print("❌ Access denied: Not a clerk")
        
        return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "message": "Only Clerk can access this route"
                }
            )

    clerk_program = request.state.user.get("program")
    print(f"➡️ Requested by: {user_email} (Role: {user_role}, Program: {clerk_program})")

    # Simplified Redis key naming
    cache_key = f"subject:{subject_id}"
    cached_subject = await redis_client.get(cache_key)

    if cached_subject:
        print(f"✅ Found data in Redis cache: {cache_key}")
    
        return JSONResponse(
                    status_code=200,
                    content={
                        "success": True,
                        "message" : "Subject Details fetched successfully",
                        "data": json.loads(cached_subject)
                    }
                )

    print("ℹ️ No cached data found — fetching from DB...")
    

    # Query all subjects by subject_code and program, and fetch linked teacher data
    subjects = await Subject.find(
        Subject.subject_code == subject_id,
        Subject.program == clerk_program,
        fetch_links=True  
    ).project(SubjectShortView).to_list()

    if not subjects:
        print(f"❌ Subjects not found: {subject_id} in Program {clerk_program}")

        
        return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "message": f"No subjects found with ID {subject_id} in Program {clerk_program}"
                }
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

    return JSONResponse(
                    status_code=200,
                    content={
                        "success": True,
                        "message" : "Subject Details fetched successfully",
                        "data": jsonable_encoder(subject_data, custom_encoder={ObjectId: str, datetime: lambda x: x.isoformat()})
                    }
                )
