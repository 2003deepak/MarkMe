from fastapi import APIRouter, Depends, Body
from app.schemas.timetable import Timetable
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.services.clerk_services.create_teacher import create_teacher
from app.services.clerk_services.create_subject import create_subject
from app.services.clerk_services.add_timetable import add_timetable
from app.middleware.is_logged_in import is_logged_in
from app.services.teacher_services.get_all_teachers import get_all_teachers
from app.services.teacher_services.get_teacher_detail import get_teacher_by_id
from fastapi import Path

# --- Pydantic Imports
from app.models.allModel import CreateSubjectRequest, TeacherRegisterRequest , TimetableRequest

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
    request: TimetableRequest,
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


# Purpose: Fetch basic information of a specific teacher
#
# Flow:
# 1. This route expects a teacher_id in the request body.
# 2. First, verify that the current user has the role 'clerk'. Only clerks are authorized to access this data.
# 3. For Version 1.0:
#    - Attempt to retrieve the teacher's basic info from Redis cache.
#    - The cache key used here is the same one stored during the `/me` route for the teacher, 
#      so there’s no need to create or duplicate a new cache key specifically for this route.
#    - If the data is present in Redis, return it directly to improve performance.
#    - If not found in cache, fallback logic (optional) can fetch from MongoDB.

# 4. For Version 2.0:
#    - Extend the response with detailed teacher information from MongoDB such as:
#        - Total hours taught
#        - Student performance stats
#        - Attendance records, etc
# 

# @router.get("/teacher/:teacherid")
# async def get_teacher(
#     request : 
#     credentials: HTTPAuthorizationCredentials = Depends(security),
#     user_data: dict = Depends(is_logged_in)
# ):
    
#     return await get_teacher(request , user_data)

@router.get("/teacher/{teacher_id}")
async def get_teacher_route(
    teacher_id: str = Path(..., description="Teacher ID to fetch details for"),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
    return await get_teacher_by_id(teacher_id, user_data)


   
    