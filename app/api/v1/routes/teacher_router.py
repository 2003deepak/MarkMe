from fastapi import APIRouter, Form, UploadFile, File, HTTPException, Depends, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import ValidationError
from typing import List, Optional
import json
import asyncio
from fastapi.responses import StreamingResponse
from app.middleware.is_logged_in import is_logged_in
from app.services.teacher_services.recognize_students import recognize_students
from app.services.teacher_services.get_teacher_detail import get_teacher_me
from app.services.teacher_services.create_session_exception import create_session_exception
from app.services.teacher_services.update_teacher_profile import update_teacher_profile
from app.services.teacher_services.mark_attendance import mark_student_attendance
from app.services.teacher_services.get_current_and_upcoming_sessions import get_current_and_upcoming_sessions
from app.services.teacher_services.fetch_class_list import fetch_class
from app.models.allModel import UpdateProfileRequest, ClassSearchRequest,CreateExceptionSession
import logging
from app.core.config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()
security = HTTPBearer()  # Define security scheme



@router.get("/me")
async def get_teacher_me_route(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
    return await get_teacher_me(user_data)

@router.put("/me/update-profile")
async def update_teacher_profile_route(
    first_name: Optional[str] = Form(None),
    middle_name: Optional[str] = Form(None),
    last_name: Optional[str] = Form(None),
    mobile_number: Optional[str] = Form(None),
    profile_picture: Optional[UploadFile] = File(None),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
    try:
        request_data = UpdateProfileRequest(
            first_name=first_name,
            middle_name=middle_name,
            last_name=last_name,
            phone=mobile_number,
        )
        return await update_teacher_profile(request_data, user_data, profile_picture)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=json.loads(e.json()))

@router.get("/current-session")
async def get_current_session(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
    return await get_current_and_upcoming_sessions(user_data)

@router.post("/session/recognize/{attendance_id}")
async def initiate_recognition(
    attendance_id: str,
    image: UploadFile = File(...),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
    return await recognize_students(attendance_id, user_data, image)


@router.post("/student/search")
async def get_class_list_for_group(
    request: ClassSearchRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in),
):
    return await fetch_class(user_data, request)


@router.post("/attendance/mark-attendance")
async def mark_attedance(
    attendance_id: str,
    attendance_student : str ,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
    return await mark_student_attendance(attendance_id, attendance_student, user_data)


@router.post("/create-exception")
async def create_exception(
    request : CreateExceptionSession,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
    return await create_session_exception(request,user_data)
