from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from app.core.database import get_db
from app.core.config import settings
from datetime import datetime, timedelta
from passlib.context import CryptContext
from app.schemas.student import Student
from pydantic import ValidationError
from app.utils.security import get_password_hash
from app.utils.token_utils import create_verification_token
from typing import List
from app.utils.publisher import send_to_queue  
from app.models.allModel import StudentRegisterRequest
from uuid import uuid4


async def register_student(student_data: StudentRegisterRequest, request: Request):
    try:
        print("Starting student registration...")

       #safe role
        user = getattr(request.state, "user", None)

        # public self registration
        if not user:
            role = "student"
        else:
            role = user.get("role")

        if role not in ["student", "clerk"]:
            return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "message": "Only student or clerk can register student"
                }
            )

        #exists
        if await Student.find_one(Student.email == student_data.email):
            return JSONResponse(
                status_code=409,
                content={
                    "success": False,
                    "message": "Student already exists "
                }
            )

        #hash
        hashed_password = get_password_hash(str(student_data.password))

        #clerk auto verify
        is_verified = False
        
        expiry = None

        if not is_verified:
            expiry = datetime.utcnow() + timedelta(days=1)

        #create
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
            is_verified=is_verified,
            verification_expires_at=expiry
        )

        await student_doc.save()

        #email only for self registration
        if not is_verified:
            token = create_verification_token(student_data.email)
            verification_link = f"{settings.BACKEND_URL}/verify-email?token={token}"

            html_body = f"""
            <html>
                <body style="font-family: Arial, sans-serif;">
                    <p>Hello <b>{student_data.first_name}</b>,</p>

                    <p>Thanks for registering on <b>MarkMe</b>!</p>

                    <p>Please verify your email by clicking the button below:</p>

                    <p>
                        <a href="{verification_link}"
                        style="
                            display: inline-block;
                            padding: 10px 16px;
                            background-color: #4CAF50;
                            color: white;
                            text-decoration: none;
                            border-radius: 4px;
                            font-weight: bold;
                        ">
                            Verify Email
                        </a>
                    </p>

                    <p>This link will expire in <b>30 minutes</b>.</p>

                    <p>If you didn’t create this account, please report to the admin.</p>

                    <br />
                    <p>Regards,<br />MarkMe Team</p>
                </body>
            </html>
            """

            await send_to_queue(
                "email_queue",
                {
                    "type": "send_email",
                    "data": {
                        "to": student_data.email,
                        "subject": "Verify your email - MarkMe",
                        "body": html_body,
                        "is_html": True   
                    }
                },
                priority=5
            )


        #response
        message = (
            "Student registered successfully. Verification email sent."
            if not is_verified else
            "Student registered successfully by clerk."
        )

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": message,
                "data": {
                    "name": f"{student_data.first_name} {student_data.last_name}".strip(),
                    "email": student_data.email,
                    "verified": is_verified
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
