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
    mode: Literal["student_listing", "attendance"] = "student_listing"
):
    user_role = request.state.user.get("role")
    if user_role not in {"teacher", "clerk"}:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"success": False, "message": "Access denied."}
        )

    department = request.state.user.get("department")
    program = program.upper().strip()

    # Cache key includes mode to avoid conflicts
    cache_key = f"class_students:{program}:{department}:{semester}:{batch_year}:{mode}"

    try:
        # Cache HIT
        cached = await redis_client.get(cache_key)
        if cached:
            return JSONResponse(status_code=status.HTTP_200_OK, content=json.loads(cached))

        # Query based on mode
        query = {
            "program": program,
            "department": department,
            "semester": semester,
            "batch_year": batch_year,
        }

        if mode == "attendance":
            query["is_verified"] = True
            projection_model = StudentBasicView
        else:
            projection_model = StudentShortView

        students_raw = await Student.find(query).project(projection_model).to_list()

        print(f"Found {len(students_raw)} students → caching as {cache_key}")

       
        students_data = [
            json.loads(student.model_dump_json(by_alias=True, exclude_unset=True))
            for student in students_raw
        ]

        response_data = {
            "success": True,
            "message": "Class fetched successfully",
            "data": students_data,
            "count": len(students_data),
            "mode": mode,
            "cached": False
        }

        # THIS IS THE KEY: Use our custom encoder
        serialized_response = json.dumps(response_data, cls=JSONEncoder)

        # Cache for 1 hour
        await redis_client.setex(cache_key, 3600, serialized_response)

        # Mark as cached for next time (optional)
        response_data["cached"] = False

        return JSONResponse(status_code=status.HTTP_200_OK, content=response_data)

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