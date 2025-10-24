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
        logging.info(f"Unauthorized access attempt by role: {user_role}")
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Only students can access this route"}
        )

    cache_key_student = f"student:{user_email}"
    cached_student = await redis_client.get(cache_key_student)

    if cached_student:
        logging.info(f"Student data for {user_email} retrieved from cache.")
        student_data = json.loads(cached_student)
        try:
            validated_student_data = StudentShortView.model_validate(student_data)
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "message": "Student detailed fetched successfully",
                    "data": validated_student_data.model_dump(exclude_none=True)
                }
            )
        except Exception as e:
            logging.warning(f"Cached student data for {user_email} is invalid: {e}. Refetching.")

    student = await Student.find_one(Student.email == user_email)
    if not student:
        logging.error(f"Student with email {user_email} not found.")
        return JSONResponse(
            status_code=404,
            content={"success": False, "message": "Student not found"}
        )

    # ✅ Format dob to DD/MM/YYYY (if exists)
    dob_str = None
    if student.dob:
        try:
            dob_str = student.dob.strftime("%d/%m/%Y")
        except Exception as e:
            logging.warning(f"Invalid DOB format for {user_email}: {e}")

    student_dict = {
        "student_id": student.id,
        "first_name": student.first_name,
        "middle_name": student.middle_name,
        "last_name": student.last_name,
        "dob": dob_str,  # ✅ formatted DOB here
        "email": student.email,
        "phone": str(student.phone) if student.phone is not None else None,
        "department": student.department,
        "program": student.program,
        "semester": student.semester,
        "batch_year": student.batch_year,
        "roll_number": student.roll_number,
        "profile_picture": student.profile_picture,
        "is_embeddings": bool(student.face_embedding)
    }

    try:
        student_out_data = StudentShortView.model_validate(student_dict)
        student_dict_for_response = student_out_data.model_dump(mode="json")
    except Exception as e:
        logging.error(f"Pydantic validation error for student {user_email}: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"Data validation error: {e}"}
        )

    await redis_client.setex(
        cache_key_student,
        3600,
        json.dumps(student_dict_for_response, cls=MongoJSONEncoder)
    )
    logging.info(f"Student data for {user_email} cached.")

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "Student detailed fetched successfully",
            "data": student_dict_for_response
        }
    )
