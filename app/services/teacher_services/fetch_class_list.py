from fastapi import status, Request
from fastapi.responses import JSONResponse
from typing import Literal
from bson import ObjectId
from datetime import datetime
import json

from app.schemas.student import Student
from app.models.allModel import StudentListingView, StudentShortView


#json encoder
class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, bytes):
            return obj.decode("utf-8")
        return super().default(obj)


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

    user = request.state.user
    role = user.get("role")

    if role not in {"teacher", "clerk"}:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"success": False, "message": "Access denied"}
        )

    # ---------------- BUILD QUERY ----------------

    base_query = {}

    #teacher logic
    if role == "teacher":

        if not (batch_year and program and semester):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "success": False,
                    "message": "Student Fetch Failed",
                    "error": "Missing required parameters for teacher role"
                }
            )

        base_query = {
            "program": program,
            "semester": semester
        }

        if batch_year:
            base_query["batch_year"] = batch_year

    #clerk logic using scopes
    else:

        scopes = user.get("academic_scopes", [])

        if not scopes:
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "message": "No students found",
                    "data": []
                }
            )

        scope_filters = []

        for scope in scopes:

            condition = {
                "program": scope["program_id"],
                "department": scope["department_id"]
            }

            if batch_year:
                condition["batch_year"] = batch_year

            if semester:
                condition["semester"] = semester

            if program:
                condition["program"] = program

            scope_filters.append(condition)

        base_query = {"$or": scope_filters}

    # ---------------- SEARCH ----------------

    if search:

        s = search.strip()

        search_filter = {
            "$or": [
                {"first_name": {"$regex": s, "$options": "i"}},
                {"last_name": {"$regex": s, "$options": "i"}},
                {"full_name": {"$regex": s, "$options": "i"}},
                {"roll_no": {"$regex": s, "$options": "i"}},
                {"email": {"$regex": s, "$options": "i"}},
            ]
        }

        if "$or" in base_query:
            query = {"$and": [base_query, search_filter]}
        else:
            query = {**base_query, **search_filter}

    else:
        query = base_query

    # ---------------- PROJECTION ----------------

    projection_model = (
        StudentListingView
        if mode == "attendance"
        else StudentShortView
    )

    # ---------------- DB FETCH ----------------

    if mode == "attendance":

        students_raw = (
            await Student.find(query)
            .project(projection_model)
            .sort("roll_no")
            .to_list()
        )

    else:

        skip = (page - 1) * limit

        total = await Student.find(query).count()

        students_raw = (
            await Student.find(query)
            .project(projection_model)
            .skip(skip)
            .limit(limit)
            .sort("roll_no")
            .to_list()
        )

    # ---------------- FORMAT RESPONSE ----------------

    students_data = []

    for st in students_raw:

        st_dict = json.loads(
            st.model_dump_json(by_alias=True, exclude_unset=True)
        )

        if mode == "student_listing":
            face_embedding = st_dict.get("face_embedding")
            st_dict["is_embeddings"] = face_embedding is not None

        st_dict.pop("face_embedding", None)

        students_data.append(st_dict)


    if mode == "student_listing":

        total_pages = (total + limit - 1) // limit

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Class fetched successfully",
                "data": students_data,
                "count": len(students_data),
                "total": total,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
                "page": page,
                "limit": limit,
                "cached": False,
                "mode": mode
            }
        )

    #attendance mode response
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "Class fetched successfully for attendance",
            "data": students_data,
            "count": len(students_data),
            "mode": mode
        }
    )