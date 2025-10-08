from fastapi import HTTPException, Request, Query
from fastapi.responses import JSONResponse
from app.core.redis import redis_client
from bson import ObjectId
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from math import ceil

from app.schemas.student_attendance_summary import StudentAttendanceSummary
from app.schemas.subject import Subject
from app.schemas.student import Student


# Custom JSON Encoder
class MongoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


async def get_critical_students(
    request: Request,
    department: Optional[str] = None,
    program: Optional[str] = None,
    semester: Optional[int] = None,
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Number of items per page"),
) -> JSONResponse:
    """
    Fetch students with attendance <= 50%, filtered by department/program/semester.
    Supports pagination via page & limit parameters.
    Returns JSONResponse with 200, 404, or 500.
    """
    try:
        # ✅ If function is called internally (not via FastAPI router),
        # the arguments will still be Query objects — handle that safely
        if hasattr(page, "default"):
            page = page.default
        if hasattr(limit, "default"):
            limit = limit.default

        page = int(page)
        limit = int(limit)

        logging.info(
            f"Received request for critical students: department={department}, program={program}, semester={semester}, page={page}, limit={limit}"
        )

        base_cache_key = f"critical_students:{department or 'any'}:{program or 'any'}:{semester or 'any'}"
        cached_full_data = await redis_client.get(base_cache_key)
        full_critical_students = None
        source = "database"

        # ✅ Try cache first
        if cached_full_data:
            logging.info(f"Cache hit for full data key: {base_cache_key}")
            try:
                full_critical_students = json.loads(cached_full_data)
                source = "cache"
            except json.JSONDecodeError:
                logging.warning(f"Invalid cache data for key: {base_cache_key}, deleting")
                await redis_client.delete(base_cache_key)

        filters_provided = any([department, program, semester])
        logging.info(f"Filters provided: {filters_provided}")

        # ✅ Fetch from DB if not cached
        if full_critical_students is None:
            summaries = await StudentAttendanceSummary.find(
                {"percentage": {"$lte": 50}},
                fetch_links=True
            ).to_list()

            logging.info(f"Fetched {len(summaries)} critical attendance summaries from DB")

            full_critical_students = []
            for summary in summaries:
                student = summary.student
                subject = summary.subject
                if not student or not subject:
                    continue

                if department and subject.department != department:
                    continue
                if program and subject.program != program:
                    continue
                if semester and subject.semester != semester:
                    continue

                full_critical_students.append({
                    "student_id": str(student.id),
                    "student_name": f"{student.first_name} {student.last_name}",
                    "department": subject.department,
                    "program": subject.program,
                    "semester": subject.semester,
                    "subject_id": str(subject.id),
                    "subject_name": getattr(subject, "subject_name", None),
                    "subject_component": getattr(subject, "component", None),
                    "percentage": summary.percentage,
                    "attended": summary.attended,
                    "total_classes": summary.total_classes
                })

            logging.info(f"After applying filters, {len(full_critical_students)} total critical students")

            # Cache for 30 minutes
            await redis_client.setex(base_cache_key, 1800, json.dumps(full_critical_students, cls=MongoJSONEncoder))
            logging.info(f"Cached {len(full_critical_students)} full critical students for key: {base_cache_key}")

        # ✅ No data for given filters → 404
        if filters_provided and not full_critical_students:
            return JSONResponse(
                status_code=404,
                content={
                    "status": "fail",
                    "message": "No critical-risk students found for the given filters",
                    "data": {},
                    "source": source
                }
            )

        # ✅ Pagination
        total_items = len(full_critical_students)
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        paginated_students = full_critical_students[start_idx:end_idx]

        pagination_info = {
            "current_page": page,
            "page_size": limit,
            "total_items": total_items,
            "total_pages": ceil(total_items / limit)
        }

        response_data = {
            "students": paginated_students,
            "pagination": pagination_info
        }

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "Critical-risk students fetched successfully",
                "data": response_data,
                "source": source
            }
        )

    except Exception as e:
        logging.error(f"💥 Error fetching critical-risk students: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Failed to fetch critical-risk students",
                "error": str(e),
                "data": {}
            }
        )
