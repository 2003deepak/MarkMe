from fastapi import APIRouter, Form, UploadFile, File, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.services.student_services.register_student import register_student
from app.schemas.student import Student
from app.models.allModel import StudentRegisterRequest
from pydantic import ValidationError
from typing import List
from datetime import date
from app.middleware.is_logged_in import is_logged_in



router = APIRouter()

@router.post("/register")
async def register_student_route(
    first_name: str = Form(...),
    middle_name: str = Form(None),
    last_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(..., min_length=6, max_length=6),
    phone: int = Form(...),
    dob: str = Form(..., description="Date of birth in YYYY-MM-DD format"),
    roll_number: int = Form(...),
    program: str = Form(...),
    department: str = Form(...),
    semester: int = Form(...),
    batch_year: int = Form(...),
    images: List[UploadFile] = File(..., description="3 to 4 photos of the student")
):
    try:
        # Validate that 3 to 4 images are provided
        if len(images) < 3 or len(images) > 4:
            raise HTTPException(
                status_code=400,
                detail="Please upload between 3 and 4 photos"
            )

        # Validate and parse dob
        try:
            dob_date = date.fromisoformat(dob)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid date format for dob. Use YYYY-MM-DD"
            )

        # Create StudentRegisterRequest object for validation
        student_request = StudentRegisterRequest(
            first_name=first_name,
            middle_name=middle_name,
            last_name=last_name,
            email=email,
            password=password,
            phone=phone,
            dob=dob_date,
            roll_number=roll_number,
            program=program,
            department=department,
            semester=semester,
            batch_year=batch_year
        )

        # Convert to Student object (with placeholders for server-generated fields)
        student_data = Student(
            student_id=f"{program.upper()}-{department.upper()}-{batch_year}-{semester}-{roll_number}",  # Generated student_id
            first_name=student_request.first_name,
            middle_name=student_request.middle_name,
            last_name=student_request.last_name,
            email=student_request.email,
            password=student_request.password,  # Will be hashed in register_student
            phone=student_request.phone,
            dob=dob,  # Converted to string for Student schema
            roll_number=student_request.roll_number,
            program=student_request.program,
            department=student_request.department,
            semester=student_request.semester,
            batch_year=student_request.batch_year,
            face_embedding=[],  # Placeholder, filled in register_student
        )

        return await register_student(
            student_data=student_data,
            images=images
        )

    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")
    

# In this route, I want to get the details of the logged-in student.
# The function should return the student's email and other details.
# The user_data should be fetched from the is_logged_in dependency, which checks the JWT token
# and returns the user data.
# Check the role of the user in user_data and ensure it is a student.
# The response should be a JSON object with the student's details.


# @router.get("/me")
# async def get_me(
#     request: , # Just ask for email of the student , Create a Pydantic Model for this
#     credentials: HTTPAuthorizationCredentials = Depends(security),
#     user_data: dict = Depends(is_logged_in)
# ):
   
#     return await function(request,user_data)



# In this route, I want to update the profile of the logged-in student.
# The request should contain the fields that can be updated :- 
# first_name , middle_name , last_name , email , profile_picture , dob , phone 
# The user_data should be fetched from the is_logged_in dependency, which checks the JWT token
# and returns the user data.
# Check the role of the user in user_data and ensure it is a student.

#router.put("/me/update-profile")
# async def update_profile(
#     request: UpdateProfileRequest,  # Define this Pydantic model for profile updates
#     credentials: HTTPAuthorizationCredentials = Depends(security),
#     user_data: dict = Depends(is_logged_in)
# ):

#     return await function(request,user_data)