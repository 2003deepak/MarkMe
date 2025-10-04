from fastapi import APIRouter, Form, Request, UploadFile, File, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from typing import List, Optional
import json
from app.services.teacher_services.recognize_students import recognize_students
from app.services.teacher_services.get_teacher_detail import get_teacher_me
from app.services.teacher_services.create_session_exception import create_session_exception
from app.services.teacher_services.update_teacher_profile import update_teacher_profile
from app.services.teacher_services.mark_attendance import mark_student_attendance
from app.services.teacher_services.get_current_and_upcoming_sessions import get_current_and_upcoming_sessions
from app.services.teacher_services.fetch_class_list import fetch_class
from app.models.allModel import UpdateProfileRequest, CreateExceptionSession
import logging
from app.core.config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()




@router.get("/me")
async def get_teacher_me_route(request : Request):
    return await get_teacher_me(request)


@router.put("/me/update-profile")
async def update_teacher_profile_route(
    request: Request,
    first_name: Optional[str] = Form(None),
    middle_name: Optional[str] = Form(None),
    last_name: Optional[str] = Form(None),
    mobile_number: Optional[str] = Form(None),  
    profile_picture: Optional[UploadFile] = File(None),
):
    try:
        request_data = UpdateProfileRequest(
            first_name=first_name,
            middle_name=middle_name,
            last_name=last_name,
            mobile_number=mobile_number,  
        )
        return await update_teacher_profile(request, request_data, profile_picture)
    except ValidationError as e:
        error_details = e.errors()
        error_msg = error_details[0]["msg"] if error_details else "Validation error"
        return JSONResponse(
            status_code=422,
            content={
                "status": "fail",
                "message": f"Validation error: {error_msg}"
            }
        )
        
@router.get("/current-session")
async def get_current_session(request: Request):
    return await get_current_and_upcoming_sessions(request)



@router.post("/session/recognize/{attendance_id}")
async def initiate_recognition(
    request : Request,
    attendance_id: str,
    images: List[UploadFile] = File(...),
):
    return await recognize_students(request,attendance_id,images)


@router.get("/student")
async def get_class_list_for_group(
    request: Request,
    batch_year: int,
    program: str,
    semester: int
):
    return await fetch_class(request, batch_year, program, semester)


@router.post("/attendance/mark-attendance")
async def mark_attendance(
    request: Request,
    attendance_id: str,
    attendance_student: str
):
    return await mark_student_attendance(request, attendance_id, attendance_student)


@router.post("/create-exception")
async def create_exception(
    request: Request,
    exception_request: CreateExceptionSession
):
    return await create_session_exception(request, exception_request)
