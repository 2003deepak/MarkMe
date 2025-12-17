from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from typing import Optional
import json

from app.core.redis import redis_client
from app.schemas.teacher import Teacher
from app.models.allModel import TeacherListingView


async def get_all_teachers(
    request: Request,
    page: int = 1,
    limit: int = 10,
    search: Optional[str] = None
):
    # --- Role check ---
    user_role = request.state.user.get("role")
    if user_role != "clerk":
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Only clerks can access this route"}
        )

    department = request.state.user.get("department")
    if not department:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Department not found"}
        )

    # --- Cache Key ---
    search_query = search.strip() if search else None
    cache_key = f"teachers:list:{department}:{search_query or 'none'}:{page}:{limit}"

    cached = await redis_client.get(cache_key)
    if cached:
        payload = json.loads(cached)
        return JSONResponse(status_code=200, content={
            **payload,
            "success": True,
            "cached": True
        })

    # --- Build Query ---
    query = Teacher.find(Teacher.department == department)

    if search_query:
        regex = {"$regex": search_query, "$options": "i"}
        query = query.find({
            "$or": [
                {"first_name": regex},
                {"last_name": regex},
                {"email": regex},
                {"mobile_number": regex},
                {"teacher_id" : regex}
            ]
        })

    # --- Total Count ---
    total = await query.count()

    # --- Pagination ---
    teachers_raw = await (
        query
        .skip((page - 1) * limit)
        .limit(limit)
        .project(TeacherListingView)
        .to_list()
    )

    # Convert projection → pure dict 
    teachers = [
        t.model_dump(mode="json", by_alias=True)
        for t in teachers_raw
    ]


    total_pages = max(1, (total + limit - 1) // limit)

    response_payload = {
        "data": teachers,
        "count": len(teachers),
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }

    # Optional: Cache the list
    encoded_payload = jsonable_encoder(response_payload)
    await redis_client.setex(cache_key, 3600, json.dumps(encoded_payload))

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "cached": False,
            **response_payload
        }
    )
