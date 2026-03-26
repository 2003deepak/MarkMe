from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from typing import Optional
import json

from app.core.redis import redis_client
from app.schemas.teacher import Teacher


async def get_all_teachers(
    request: Request,
    department: str | None = None,
    program: str | None = None,
    page: int = 1,
    limit: int = 10,
    search: Optional[str] = None
):

    user = request.state.user
    role = user.get("role")

    #auth
    if role != "clerk":
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "message": "Only clerks can access this route"
            }
        )

    scopes = user.get("academic_scopes", [])

    if not scopes:
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": [],
                "message": "No teachers found"
            }
        )

    clerk_id = user.get("id")

    search_query = search.strip() if search else None

    cache_key = f"teachers:list:{clerk_id}:{program or 'all'}:{department or 'all'}:{search_query or 'none'}:{page}:{limit}"

    cached = await redis_client.get(cache_key)

    if cached:
        payload = json.loads(cached)
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "cached": True,
                **payload
            }
        )

    skip = (page - 1) * limit

    #validate program/department inside scope
    scope_filters = []

    if program or department:
        valid = False

        for scope in scopes:
            if program and department:
                if scope["program_id"] == program and scope["department_id"] == department:
                    valid = True
                    break

            elif program:
                if scope["program_id"] == program:
                    valid = True

            elif department:
                if scope["department_id"] == department:
                    valid = True

        if not valid:
            return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "message": "Requested program/department not in your scope"
                }
            )

        #build specific filter
        specific_filter = {}

        if program:
            specific_filter["subjects.program"] = program

        if department:
            specific_filter["subjects.department"] = department

        scope_filters.append(specific_filter)

    else:
        #fallback to all scopes
        for scope in scopes:
            scope_filters.append({
                "subjects.program": scope["program_id"],
                "subjects.department": scope["department_id"]
            })

    #search filter
    search_filter = {}

    if search_query:
        regex = {"$regex": search_query, "$options": "i"}

        search_filter = {
            "$or": [
                {"first_name": regex},
                {"last_name": regex},
                {"email": regex},
                {"teacher_id": regex},
                {"mobile_number": regex}
            ]
        }

    pipeline = [

        #join subjects
        {
            "$lookup": {
                "from": "subjects",
                "localField": "subjects_assigned.$id",
                "foreignField": "_id",
                "as": "subjects"
            }
        },

        #unwind subjects
        {
            "$unwind": "$subjects"
        },

        #match scope
        {
            "$match": {
                "$or": scope_filters
            }
        },

        #group teachers
        {
            "$group": {
                "_id": {"$toString": "$_id"},
                "teacher_id": {"$first": "$teacher_id"},
                "first_name": {"$first": "$first_name"},
                "last_name": {"$first": "$last_name"},
                "email": {"$first": "$email"},
                "mobile_number": {"$first": "$mobile_number"},
                "profile_picture": {"$first": "$profile_picture"}
            }
        }

    ]

    if search_filter:
        pipeline.append({"$match": search_filter})

    #count
    count_pipeline = pipeline + [{"$count": "total"}]
    count_result = await Teacher.aggregate(count_pipeline).to_list()
    total = count_result[0]["total"] if count_result else 0

    #pagination
    pipeline.extend([
        {"$sort": {"first_name": 1}},
        {"$skip": skip},
        {"$limit": limit}
    ])

    teachers = await Teacher.aggregate(pipeline).to_list()

    total_pages = max(1, (total + limit - 1) // limit)

    response_payload = {
        "data": jsonable_encoder(teachers),
        "count": len(teachers),
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1
    }

    await redis_client.setex(
        cache_key,
        3600,
        json.dumps(response_payload)
    )

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "cached": False,
            **response_payload
        }
    )