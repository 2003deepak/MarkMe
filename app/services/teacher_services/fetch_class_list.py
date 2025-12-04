from fastapi import status, Request
from fastapi.responses import JSONResponse
from typing import Literal
from bson import ObjectId
from datetime import datetime
import json

from app.schemas.student import Student
from app.models.allModel import StudentBasicView, StudentShortView
from app.core.redis import redis_client


# -------------------------------------------------------
# Custom JSON Encoder
# -------------------------------------------------------
class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, bytes):
            return obj.decode("utf-8")
        return super().default(obj)


# -------------------------------------------------------
# MAIN CONTROLLER
# -------------------------------------------------------
async def fetch_class(
    request: Request,
    batch_year: int | None = None,
    program: str | None = None,
    semester: int | None = None,
    mode: Literal["student_listing", "attendance"] = "student_listing",
    page: int = 1,
    limit: int = 10,
    search: str | None = None
):

    user_role = request.state.user.get("role")
    department = request.state.user.get("department")

    print(f"[ROLE] User Role: {user_role}, Department: {department}")

    # Role Guard
    if user_role not in {"teacher", "clerk"}:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"success": False, "message": "Access denied."}
        )

    # Teachers must provide filters
    if user_role == "teacher":
        if not (batch_year and program and semester):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"success": False, "message": "Teacher must provide batch_year, program and semester."}
            )

    # Cache Key generation
    key_program = program or "ALL"
    key_semester = semester or "ALL"
    key_batch = batch_year or "ALL"

    cache_key = f"class_students_data:{user_role}:{department}:{key_program}:{key_semester}:{key_batch}:{mode}"

    if search:
        cache_key += f":search={search.strip()}"

    cache_key += f":page={page}:limit={limit}"

    # -------------------------------------------------------
    # CACHE CHECK (only for student data)
    # -------------------------------------------------------
    cached = await redis_client.get(cache_key)
    if cached:
        print("[CACHE-HIT] Returning cached data")
        cached_obj = json.loads(cached)

        students_data = cached_obj["data"]
        meta = cached_obj["meta"]

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Class fetched successfully (cached)",
                "data": students_data,
                "count": meta["count"],
                "total": meta["total"],
                "total_pages": meta["total_pages"],
                "has_next": meta["has_next"],
                "has_prev": meta["has_prev"],
                "page": page,
                "limit": limit,
                "cached": True,
                "mode": mode
            }
        )

    # -------------------------------------------------------
    # BUILD QUERY
    # -------------------------------------------------------
    query = {"department": department}

    if program:
        query["program"] = program
    if batch_year:
        query["batch_year"] = batch_year
    if semester:
        query["semester"] = semester

    print(f"[QUERY] {query}")

    # Mode-based projection
    projection_model = StudentShortView
    
    if mode == "attendance":
        projection_model = StudentBasicView

    # Search filter
    if search:
        s = search.strip()
        query["$or"] = [
            {"first_name": {"$regex": s, "$options": "i"}},
            {"last_name": {"$regex": s, "$options": "i"}},
            {"full_name": {"$regex": s, "$options": "i"}},
            {"roll_no": {"$regex": s, "$options": "i"}},
            {"email": {"$regex": s, "$options": "i"}}
        ]
        print(f"[SEARCH] Filter added: {s}")

    # -------------------------------------------------------
    # DB FETCH
    # -------------------------------------------------------
    skip = (page - 1) * limit

    total = await Student.find(query).count()

    students_raw = (
        await Student.find(query)
        .project(projection_model)
        .skip(skip)
        .limit(limit)
        .to_list()
    )


    # FORMAT DATA
    students_data = []

    for st in students_raw:
        st_dict = json.loads(st.model_dump_json(by_alias=True, exclude_unset=True))
        
        if mode == 'student_listing' : 

            # Fix is_embeddings
            face_embedding = st_dict.get("face_embedding")
            st_dict["is_embeddings"] = face_embedding is not None

        # Remove embedding from output
        st_dict.pop("face_embedding", None)

        students_data.append(st_dict)
        
        
    # SAVE TO CACHE (only data)
    await redis_client.setex(
    cache_key,
    3600,
    json.dumps({
        "data": students_data,
        "meta": {
            "count": len(students_data),
            "total": total,
            "total_pages": (total + limit - 1) // limit,
            "has_next": page < ((total + limit - 1) // limit),
            "has_prev": page > 1
        }
    }, cls=JSONEncoder)
)


    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "Class fetched successfully",
            "data": students_data,
            "count": len(students_data),
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit,
            "has_next": page < ((total + limit - 1) // limit),
            "has_prev": page > 1,
            "cached": False,
            "mode": mode
        }
    )
