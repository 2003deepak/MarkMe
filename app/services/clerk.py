from fastapi import HTTPException
import random
from app.core.security import get_password_hash
from app.schemas.subject import Subject
from app.schemas.teacher import Teacher
from app.schemas.otp import OTP
from app.core.mail_config import send_email


async def create_subject(data: dict):
    required_fields = [
        "subject_name",
        "subject_code",
        "department",
        "semester",
        "program",
        "type",
        "credit_hours"
    ]
    for field in required_fields:
        if field not in data:
            raise HTTPException(
                status_code=400,
                detail={
                    "status": "fail",
                    "message": f"Missing field: {field}"
                }
            )

    subject = Subject(**data)
    await subject.insert()

    return {
        "status": "success",
        "message": "Subject created successfully"
    }


async def create_teacher(data: dict):
    required_fields = [
        "first_name",
        "last_name",
        "email",
        "phone",
        "dob",
        "roll_number",
        "departments",
        "title",
        "subjects",
        "teacherId"
    ]
    for field in required_fields:
        if field not in data:
            raise HTTPException(
                status_code=400,
                detail={
                    "status": "fail",
                    "message": f"Missing field: {field}"
                }
            )

    raw_password = str(random.randint(100000, 999999))
    data['password'] = raw_password  # plain 6-digit PIN

    teacher = Teacher(**data)
    await teacher.insert()

    await send_email(
        subject="Your Teacher Account Password",
        email_to=data["email"],
        body=f"<p>Welcome, Teacher!<br>Your password is <strong>{raw_password}</strong>.</p>"
    )

    return {
        "status": "success",
        "message": "Teacher created successfully",
        "data": {
            "generated_password": raw_password
        }
    }
