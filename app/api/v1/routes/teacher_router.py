from fastapi import APIRouter, Form, UploadFile, File, HTTPException, Depends, Query
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
from app.models.allModel import UpdateProfileRequest, ClassSearchRequest,CreateExceptionSession
import logging
from app.core.config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()




@router.get("/me")
async def get_teacher_me_route():
    return await get_teacher_me()

@router.put("/me/update-profile")
async def update_teacher_profile_route(
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
            phone=mobile_number,
        )
        return await update_teacher_profile(request_data,profile_picture)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=json.loads(e.json()))

@router.get("/current-session")
async def get_current_session():
    return await get_current_and_upcoming_sessions()


# This route for face recognition 
# Currently it works only for a single image upload , but it can expect or teacher can upload
# Multiple images of the class :- 

# 1) Properly enqueue the job with multiple images 
# 2) Worker :- worker_face_recognition is responsible for image recogniton 
# 3) Make it work with multiple images also 
# 4) Save the recognized students in the set , to prevent identity repetition 
# 5) I have used redis pub sub :- when ever a face is recognized , i publish a msg to f"face_progress:{attendance_id}"
# 6) So when update is recived i send it to SSE to frontend 
# 7) There is a index.html file inside utils ( that connects to sse )
# 8) As data is recieved , the card should be populated 
@router.post("/session/recognize/{attendance_id}")
async def initiate_recognition(
    attendance_id: str,
    images: List[UploadFile] = File(...),
):
    return await recognize_students(attendance_id,images)


@router.post("/student/search")
async def get_class_list_for_group(
    request: ClassSearchRequest,
   
):
    return await fetch_class(request)


@router.post("/attendance/mark-attendance")
async def mark_attedance(
    attendance_id: str,
    attendance_student : str ,
    
):
    return await mark_student_attendance(attendance_id, attendance_student)


@router.post("/create-exception")
async def create_exception(
    request : CreateExceptionSession,
    
):
    return await create_session_exception(request)
