from fastapi import Request
from fastapi.responses import JSONResponse
from datetime import datetime
import json
import logging
from bson import ObjectId
from app.core.redis import redis_client
from app.schemas.student import Student
from app.models.allModel import StudentShortView


class MongoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


async def get_student_detail(request: Request):
    user_email = request.state.user.get("email")
    user_role = request.state.user.get("role")

    if not user_email:
        return JSONResponse(
            status_code=401,
            content={"success": False, "message": "User email not found in request"}
        )

    if user_role != "student":
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Only students can access this route"}
        )

    cache_key_student = f"student:{user_email}"
    cached_student = await redis_client.get(cache_key_student)

    if cached_student:
        student_data = json.loads(cached_student)
        try:
            validated = StudentShortView.model_validate(student_data)
            response_data = validated.model_dump(mode="json")

            # ✅ Format DOB ONLY FOR RESPONSE
            if response_data.get("dob"):
                response_data["dob"] = datetime.fromisoformat(
                    response_data["dob"]
                ).strftime("%d/%m/%Y")

            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "message": "Student details fetched successfully",
                    "data": response_data
                }
            )
        except Exception:
            pass  # fallback to DB fetch

    student = await Student.find_one(Student.email == user_email)
    if not student:
        return JSONResponse(
            status_code=404,
            content={"success": False, "message": "Student not found"}
        )

    # ✅ Keep DOB as datetime
    student_dict = {
        "student_id": student.id,
        "first_name": student.first_name,
        "middle_name": student.middle_name,
        "last_name": student.last_name,
        "dob": student.dob,   # ✅ datetime
        "email": student.email,
        "phone": str(student.phone) if student.phone else None,
        "department": student.department,
        "program": student.program,
        "semester": student.semester,
        "batch_year": student.batch_year,
        "roll_number": student.roll_number,
        "profile_picture": student.profile_picture,
        "is_embeddings": bool(student.face_embedding),
        "created_at": student.created_at
    }

    validated = StudentShortView.model_validate(student_dict)
    response_data = validated.model_dump(mode="json")

    # ✅ Format DOB ONLY FOR RESPONSE
    if response_data.get("dob"):
        response_data["dob"] = datetime.fromisoformat(
            response_data["dob"]
        ).strftime("%d/%m/%Y")

    await redis_client.setex(
        cache_key_student,
        3600,
        json.dumps(response_data, cls=MongoJSONEncoder)
    )

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "Student details fetched successfully",
            "data": response_data
        }
    )
