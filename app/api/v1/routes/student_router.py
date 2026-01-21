from fastapi import APIRouter, Form, Request, UploadFile, File, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from app.services.student_services.bunk_safety_calculator import get_tomorrow_bunk_safety, get_week_plan
from app.services.student_services.get_upcoming_session import get_todays_upcoming_sessions_for_student
from app.services.student_services.register_student import register_student
from app.services.student_services.get_student_detail import get_student_detail
from app.services.student_services.update_student_profile import update_student_profile
from app.services.student_services.verify_student import verify_student_email
from typing import List, Optional
from datetime import datetime
# -- Pydantic Model Import
from app.models.allModel import StudentRegisterRequest, UpdateProfileRequest 

router = APIRouter()


@router.post("/")
async def register_student_route(student_data : StudentRegisterRequest ,  request: Request):
    try:
         return await register_student(student_data, request)

    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except HTTPException as e:
        raise e
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@router.get("/me")
async def get_me(request: Request):
    
    return await get_student_detail(request)

@router.get("/current-session")
async def get_current_session(request: Request):
    return await get_todays_upcoming_sessions_for_student(request)


@router.put("/me/update-profile")
async def update_profile(
    request: Request,
    first_name: Optional[str] = Form(None),
    middle_name: Optional[str] = Form(None),
    last_name: Optional[str] = Form(None),
    # email: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    dob: Optional[str] = Form(None, description="Date of birth in YYYY-MM-DD format"),
    roll_number: Optional[str] = Form(None),
    program: Optional[str] = Form(None),
    department: Optional[str] = Form(None),
    semester: Optional[str] = Form(None),
    batch_year: Optional[str] = Form(None),
    images: List[UploadFile] = File(default_factory=list),
    profile_picture: Optional[UploadFile] = File(None),
):

    # Parse dob string to date object if provided
    dob_date = None
    if dob:
        try:
            dob_date = datetime.strptime(dob, "%Y-%m-%d").date()
        except ValueError:
            return JSONResponse(
                success_code=422,
                content={
                    "success": False, 
                    "message": "Invalid date format for dob. Use YYYY-MM-DD."
                }
            )

    # Parse numeric fields
    roll_number_int = None
    if roll_number:
        try:
            roll_number_int = int(roll_number)
        except ValueError:
            return JSONResponse(
                success_code=422,
                content={
                    "success": False, 
                    "message": "Invalid roll number format"
                }
            )

    semester_int = None
    if semester:
        try:
            semester_int = int(semester)
        except ValueError:
            return JSONResponse(
                success_code=422,
                content={
                    "success": False, 
                    "message": "Invalid semester format"
                }
            )

    batch_year_int = None
    if batch_year:
        try:
            batch_year_int = int(batch_year)
        except ValueError:
            return JSONResponse(
                success_code=422,
                content={
                    "success": False, 
                    "message": "Invalid batch year format"
                }
            )

    update_request_data = UpdateProfileRequest(
        first_name=first_name,
        middle_name=middle_name,
        last_name=last_name,
        phone=phone,
        dob=dob_date,
        roll_number=roll_number_int,
        program=program,
        department=department,
        semester=semester_int,
        batch_year=batch_year_int,
    )

    return await update_student_profile(
        request=request,
        request_data=update_request_data,
        images=images,
        profile_picture=profile_picture
    )
    
@router.post("/verify-email")
async def verify_email(request: Request):
    return await verify_student_email(request)


@router.get("/tomorrow-bunk-safety")
async def bunk_safety(request: Request):
    return await get_tomorrow_bunk_safety(request)

@router.get("/weekly-bunk-safety")
async def bunk_safety_weekly(request: Request):
    return await get_week_plan(request)


