from fastapi import status, Request
from fastapi.responses import JSONResponse
from typing import Literal
from bson import ObjectId
from datetime import datetime
import json

from app.schemas.student import Student
from app.models.allModel import StudentBasicView, StudentShortView
from app.core.redis import redis_client


# Custom JSON encoder that handles ObjectId, datetime, etc.
class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, bytes):
            return obj.decode('utf-8')
        return super().default(obj)


async def fetch_class(
    request: Request,
    batch_year: int,
    program: str,
    semester: int,
    mode: Literal["student_listing", "attendance"] = "student_listing",
    page: int = 1,
    limit: int = 10,
):
    user_role = request.state.user.get("role")
    if user_role not in {"teacher", "clerk"}:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"success": False, "message": "Access denied."}
        )

    department = request.state.user.get("department")
    program = program.upper().strip()

    # Cache key now includes page + limit
    cache_key = (
        f"class_students:{program}:{department}:{semester}:{batch_year}:"
        f"{mode}:page={page}:limit={limit}"
    )

    try:
        # Cache HIT
        cached = await redis_client.get(cache_key)
        if cached:
            return JSONResponse(
                status_code=status.HTTP_200_OK, 
                content=json.loads(cached)
            )

        # Query
        query = {
            "program": program,
            "department": department,
            "semester": semester,
            "batch_year": batch_year,
        }

        # Add condition for attendance mode
        projection_model = StudentShortView
        if mode == "attendance":
            query["is_verified"] = True
            projection_model = StudentBasicView

        # ---- Pagination ----
        skip = (page - 1) * limit

        # Count total matching docs (without pagination)
        total = await Student.find(query).count()

        # Fetch paginated results
        students_raw = (
            await Student.find(query)
            .project(projection_model)
            .skip(skip)
            .limit(limit)
            .to_list()
        )

        students_data = [
            json.loads(student.model_dump_json(by_alias=True, exclude_unset=True))
            for student in students_raw
        ]

        total_pages = (total + limit - 1) // limit

        response_data = {
            "success": True,
            "message": "Class fetched successfully",
            "data": students_data,
            "count": len(students_data),
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
            "mode": mode,
            "cached": False,
        }

        # Serialize & cache
        serialized_response = json.dumps(response_data, cls=JSONEncoder)
        await redis_client.setex(cache_key, 3600, serialized_response)

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_data
        )

    except Exception as e:
        print(f"Error in fetch_class: {type(e).__name__}: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "message": "Failed to fetch class data",
                "detail": str(e) if "dev" in request.app.state.ENV.lower() else None
            }
        )
