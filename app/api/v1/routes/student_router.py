from fastapi import APIRouter, Form, UploadFile, File, HTTPException, Depends, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.services.student_services.register_student import register_student
from app.services.student_services.get_student_detail import get_student_detail
from app.services.student_services.update_student_profile import update_student_profile
from app.services.student_services.verify_student import verify_student_email
from app.schemas.student import Student
from pydantic import ValidationError, BaseModel, EmailStr
from typing import List, Optional, Union  
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
    last_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(..., min_length=6, max_length=6),    
):
    try:
        # Create StudentRegisterRequest object for validation
        student_request = StudentRegisterRequest(
            first_name=first_name,
            last_name=last_name,
            email=email,
            password=password,
        )
        
        return await register_student(
            student_data=student_request,
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
    email: Optional[EmailStr] = Form(None),
    password: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    dob: Optional[str] = Form(None, description="Date of birth in YYYY-MM-DD format"),
    roll_number: Optional[str] = Form(None),
    program: Optional[str] = Form(None),
    department: Optional[str] = Form(None),
    semester: Optional[str] = Form(None),
    batch_year: Optional[str] = Form(None),
    images: List[UploadFile] = File(default_factory=list),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in),
):
    # Debug logging to inspect incoming values
    print(f"Received inputs: dob={dob}, roll_number={roll_number}, semester={semester}, batch_year={batch_year}, images={images}")

    # Convert empty strings to None
    def clean(value: Optional[str]) -> Optional[str]:
        return None if value is None or str(value).strip() == "" else value

    # Clean string inputs
    first_name = clean(first_name)
    middle_name = clean(middle_name)
    last_name = clean(last_name)
    email = clean(email)
    password = clean(password)
    phone = clean(phone)
    program = clean(program)
    department = clean(department)
    dob = clean(dob)  # Explicitly clean dob to handle empty string

    # Parse integer fields manually
    def parse_int(value: Optional[str], field_name: str) -> Optional[int]:
        if value is None or str(value).strip() == "":
            return None
        try:
            return int(value.strip())
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail={"status": "fail", "message": f"Invalid integer value for {field_name}"}
            )

    roll_number_int = parse_int(roll_number, "roll_number")
    semester_int = parse_int(semester, "semester")
    batch_year_int = parse_int(batch_year, "batch_year")

    # Handle dob parsing
    parsed_dob: Optional[date] = None
    if dob:  # Only attempt parsing if dob is not None or empty
        try:
            parsed_dob = datetime.strptime(dob, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail={"status": "fail", "message": "Invalid date format for dob. Use YYYY-MM-DD."}
            )

    # Normalize images
    images = images or []  # Ensure images is a list, default to empty list if None

    update_request_data = UpdateProfileRequest(
        first_name=first_name,
        middle_name=middle_name,
        last_name=last_name,
        email=email,
        password=password,
        phone=phone,
        dob=parsed_dob,
        roll_number=roll_number_int,
        program=program,
        department=department,
        semester=semester_int,
        batch_year=batch_year_int,
    )

    return await update_student_profile(
        request_data=update_request_data,
        user_data=user_data,
        images=images
    )
    
    
@router.get("/verify-email")
async def verify_email(token: str = Query(..., description="JWT verification token")):
    """
    Endpoint to verify student email using token.
    Example: GET /verify-email?token=XYZ
    """
    return await verify_student_email(token)