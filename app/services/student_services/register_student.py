from fastapi import HTTPException, UploadFile
from fastapi.responses import JSONResponse
from app.core.database import get_db
from app.core.config import settings
from datetime import datetime
from passlib.context import CryptContext
from app.schemas.student import Student
from pydantic import ValidationError
from app.utils.security import get_password_hash
from app.utils.token_utils import create_verification_token
from typing import List
from app.utils.publisher import send_to_queue  
from app.models.allModel import StudentRegisterRequest
from uuid import uuid4


async def register_student(student_data: StudentRegisterRequest):
    try:
        print("Starting student registration...")

        # ✅ Check if student already exists
        if await Student.find_one(Student.email == student_data.email):
            
            return JSONResponse(
            status_code=409,  
            content={
                "success": False,
                "message": "Student already exists "
            }
        )

        # ✅ Hash password
        hashed_password = get_password_hash(str(student_data.password))

        # ✅ Create student record with is_verified=False
        student_doc = Student(
            first_name=student_data.first_name,
            middle_name=None,
            last_name=student_data.last_name,
            email=student_data.email,
            password=hashed_password,
            phone=None,
            dob=None,
            roll_number=None,
            program=None,
            department=None,
            semester=None,
            batch_year=None,
            face_embedding=None,
            is_verified=False  
        )

        await student_doc.save()

        # ✅ Generate JWT verification token
        token = create_verification_token(student_data.email)
        verification_link = f"{settings.BACKEND_URL}/verify-email?token={token}"

        # ✅ Send Verification Email via Queue
        await send_to_queue("email_queue", {
            "type": "send_email",
            "data": {
                "to": student_data.email,
                "subject": "Verify your email - MarkMe",
                "body": (
                    f"Hello {student_data.first_name},\n\n"
                    f"Thanks for registering on MarkMe! Please verify your email by clicking the link below:\n\n"
                    f"{verification_link}\n\n"
                    "This link will expire in 30 minutes.\n\n"
                    "If you didn’t create this account, please ignore this email."
                )
            }
        }, priority=5)
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Student registered successfully. Verification email sent.",
                "data": {
                    "name": f"{student_data.first_name} {student_data.last_name}".strip(),
                    "email": student_data.email
                }
            }
        )

    except ValidationError as e:
        error = e.errors()[0]
        loc = ".".join(str(x) for x in error["loc"])
        msg = error["msg"]
        error_msg = f"Invalid {loc}: {msg.lower()}"
        if loc == "password" and "string_too_long" in str(error["type"]):
            error_msg = "Password must be exactly 6 characters"
        elif loc == "password" and "string_too_short" in str(error["type"]):
            error_msg = "Password must be at least 6 characters"

        
        return JSONResponse(
            status_code=422,
            content={
                "success": False, 
                "message": error_msg 
            }
        )
    

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in register_student: {str(e)}")

        return JSONResponse(
            status_code=500,
            content={
                "success": False, 
                "message": f"Error registering student: {str(e)}"
            }
        )