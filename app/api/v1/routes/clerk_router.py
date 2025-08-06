from fastapi import APIRouter, Depends, Body,Path
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.services.clerk_services.create_teacher import create_teacher
from app.services.clerk_services.create_subject import create_subject
from app.services.clerk_services.add_timetable import add_timetable
from app.middleware.is_logged_in import is_logged_in
from app.services.teacher_services.get_all_teachers import get_all_teachers
from app.services.teacher_services.get_teacher_detail import get_teacher_by_id
from app.services.clerk_services.get_subject_detail import get_subject_detail,get_subject_by_id


# --- Pydantic Imports
from app.models.allModel import CreateSubjectRequest, TeacherRegisterRequest , TimeTableRequest

router = APIRouter()
security = HTTPBearer()  # Define security scheme

@router.post("/subject/create")
async def create_subject_route(
    request: CreateSubjectRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
    
    return await create_subject(request,user_data)

@router.post("/teacher/create")
async def create_teacher_route(
    request: TeacherRegisterRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
   
    return await create_teacher(request,user_data)



@router.post("/timetable/create")
async def create_timetable(
    request: TimeTableRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
    
    return await add_timetable(request,user_data)



@router.get("/teacher")
async def get_all_teachers_route(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
    return await get_all_teachers(user_data)



@router.get("/teacher/{teacher_id}")
async def get_teacher_route(
    teacher_id: str = Path(..., description="Teacher ID to fetch details for"),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
    return await get_teacher_by_id(teacher_id, user_data)


@router.get("/subject")
async def get_subject(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
    return await get_subject_detail(user_data)



# ----------------------------
# Planning for Version 2.0
# ----------------------------
# In Version 2.0, we will go beyond just the subject metadata.
# For the given subject_id, we plan to compute and return:
#   - Total number of classes held
#   - Average attendance percentage of the class
#   - List of high-performing students (consistently present)
#   - List of low-performing students (frequently absent)
#   - Trends or graphs for attendance (optional in future)
#   - Possibly identify anomalies like "present in all classes" or "present in none"



@router.get("/subject/{subject_id}")
async def get_subject_by_id_route(
    subject_id: str = Path(..., description="Subject ID to fetch details for"),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
    return await get_subject_by_id(subject_id, user_data)