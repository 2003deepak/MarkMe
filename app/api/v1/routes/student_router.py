from fastapi import APIRouter, Depends
from app.services.student import register_student
from fastapi import Body

router = APIRouter()


# Ask first name, middle name ( optional ) , last name, email, mobile number, 6 digit pin , dob , roll number, program, department, semester, batch year , 3-4 photos 
# Now construct unique student ID using Program, Department, Batch Year, Semester, Roll Number
# Ex : BTECH-CSE-2023-1-12345
# Convert the students photo in vector embeddings of 512 array size 


# @router.post("/register")


@router.post("/register")
async def register_student_route(data: dict = Body(...)):
    return await register_student(data)
