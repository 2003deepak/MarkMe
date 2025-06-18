from fastapi import APIRouter, Depends
from app.services.clerk import create_subject, create_teacher
from fastapi import Body


router = APIRouter()


# Ask for subject name, subject code, department, semester, program ,  # type (Lecture/Lab), credit hours
# Save the subject in the database

# @router.post("/subject/create")



# Ask for first name, middle_name , last name, email, mobile number, password ( generate random ), dob, roll number, department, title , subject assiggned ( array fo subjects )

# @router.post("/teacher/create")


router = APIRouter()

@router.post("/subject/create")
async def create_subject_route(data: dict = Body(...)):
    return await create_subject(data)

@router.post("/teacher/create")
async def create_teacher_route(data: dict = Body(...)):
    return await create_teacher(data)