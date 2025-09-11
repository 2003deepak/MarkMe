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
from app.models.allModel import VerifyEmailRequest

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
    phone: Optional[str] = Form(None),
    dob: Optional[str] = Form(None, description="Date of birth in YYYY-MM-DD format"),
    roll_number: Optional[str] = Form(None),
    program: Optional[str] = Form(None),
    department: Optional[str] = Form(None),
    semester: Optional[str] = Form(None),
    batch_year: Optional[str] = Form(None),
    images: List[UploadFile] = File(default_factory=list),
    profile_picture: Optional[UploadFile] = File(None),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in),
):

    # Parse dob string to date object if provided
    dob_date = None
    if dob:
        try:
            dob_date = datetime.strptime(dob, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail={"status": "fail", "message": "Invalid date format for dob. Use YYYY-MM-DD."}
            )

    update_request_data = UpdateProfileRequest(
        first_name=first_name,
        middle_name=middle_name,
        last_name=last_name,
        email=email,
        phone=phone,
        dob=dob_date,
        roll_number=int(roll_number) if roll_number else None,
        program=program,
        department=department,
        semester=int(semester) if semester else None,
        batch_year=int(batch_year) if batch_year else None,
    )

    return await update_student_profile(
        request_data=update_request_data,
        user_data=user_data,
        images=images,
        profile_picture=profile_picture
    )
    
    
@router.post("/verify-email")
async def verify_email(request: VerifyEmailRequest):
    """
    Endpoint to verify student email using a JWT token provided in the request body.
    Example: POST /verify-email
    Body: {"token": "XYZ"}
    """
    return await verify_student_email(request.token)