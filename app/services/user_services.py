from app.schemas.student import Student
from app.schemas.teacher import Teacher
from app.schemas.clerk import Clerk
from typing import Optional

async def get_user_by_email_role(email: str, role: str) -> Optional[dict]:
    if role.lower() == "student":
        return await Student.find_one(Student.email == email)
    elif role.lower() == "teacher":
        return await Teacher.find_one(Teacher.email == email)
    elif role.lower() == "clerk":
        return await Clerk.find_one(Clerk.email == email)
    else:
        return None
