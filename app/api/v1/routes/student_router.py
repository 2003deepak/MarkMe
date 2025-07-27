from fastapi import APIRouter, Form, UploadFile, File, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.services.student_services.register_student import register_student
from app.services.student_services.get_student_detail import get_student_detail
from app.services.student_services.update_student_profile import update_student_profile
from app.schemas.student import Student
from pydantic import ValidationError, BaseModel
from typing import List, Optional
from datetime import datetime , date
import json
from app.middleware.is_logged_in import is_logged_in

# -- Pydantic Model Import
from app.models.allModel import StudentRegisterRequest, UpdateProfileRequest # Assuming UpdateProfileRequest is in allModel

router = APIRouter()
security = HTTPBearer()  # Define security scheme


@router.post("/register")
async def register_student_route(
    first_name: str = Form(...),
    middle_name: str = Form(None),
    last_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(..., min_length=6, max_length=6),
    phone: str = Form(...),
    dob: date = Form(..., description="Date of birth in YYYY-MM-DD format"), 
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

       

        # Create StudentRegisterRequest object for validation
        student_request = StudentRegisterRequest(
            first_name=first_name,
            middle_name=middle_name,
            last_name=last_name,
            email=email,
            password=password,
            phone=phone,
            dob=dob,
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
            face_embedding= None,  # Placeholder, filled in register_student
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
        print(e)
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/me")
async def get_me(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
    
    return await get_student_detail(user_data)


@router.put("/me/update-profile")
async def update_profile(
    first_name: Optional[str] = Form(None),
    middle_name: Optional[str] = Form(None),
    last_name: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    dob: Optional[str] = Form(None, description="Date of birth in YYYY-MM-DD format"),
    profile_picture: Optional[UploadFile] = File(None),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
   
    if first_name == "":
        first_name = None
    if middle_name == "":
        middle_name = None
    if last_name == "":
        last_name = None
    if phone == "": # Add this for phone as well
        phone = None

    # Handle dob: convert to date object or ensure None
    parsed_dob: Optional[date] = None
    if dob:
        # If dob is an empty string, treat it as None
        if dob.strip() == "":
            parsed_dob = None
        else:
            try:
                parsed_dob = datetime.strptime(dob, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(
                    status_code=422,
                    detail={"status": "fail", "message": "Invalid date format for dob. Use YYYY-MM-DD."}
                )
   
    update_request_data = UpdateProfileRequest(
        first_name=first_name,
        middle_name=middle_name,
        last_name=last_name,
        phone=phone,
        dob=parsed_dob,
    )

    return await update_student_profile(
        request_data=update_request_data,
        user_data=user_data,
        profile_picture=profile_picture
    )
