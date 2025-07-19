from fastapi import APIRouter, Depends, Body,Path
from app.schemas.timetable import Timetable
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.services.clerk_services.create_teacher import create_teacher
from app.services.clerk_services.create_subject import create_subject
from app.services.clerk_services.add_timetable import add_timetable
from app.middleware.is_logged_in import is_logged_in
from app.services.teacher_services.get_all_teachers import get_all_teachers
from app.services.teacher_services.get_teacher_detail import get_teacher_by_id
from app.services.clerk_services.get_subject_detail import get_subject_detail,get_subject_by_id


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



@router.get("/teacher/{teacher_id}")
async def get_teacher_route(
    teacher_id: str = Path(..., description="Teacher ID to fetch details for"),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
    return await get_teacher_by_id(teacher_id, user_data)


# In this route, fetch all subjects listed under the clerk's respective department
# Step 1: Check the role of the user (from the token). Proceed only if the user is a "clerk"
# Step 2: This will be a GET request and does not require a request body
# Step 3: Fetch the department of the logged-in clerk (from the user data)
# Step 4: Check if the subjects for this department are already stored in Redis Cache
#         - If cached data exists, return it directly
#         - If not, fetch the subject list from MongoDB where department matches
#           - While fetching from MongoDB, exclude the fields: created_at and updated_at
#           - Store the subject list efficiently in Redis cache for future use
# Step 5: Return the subject list as the response

# Note ( Pls refer to the code in app/services/teacher_services/get_all_teachers.py for implementation details):
# ( This functions is having similar implementation as get_all_teachers function in app/services/teacher_services/get_all_teachers.py)

@router.get("/subject")
async def get_subject(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
    return await get_subject_detail(user_data)



# In this route, fetch detailed data for a specific subject listed under the clerk's respective department

# Step 1: Verify the user's role using the token — only allow access if the user is a "clerk"

# Step 2: This is a GET request — the subject_id will be passed as a path parameter (not in the body)

# Step 3: From the DB extract the department associated with the logged-in clerk

# Step 4: Check if subject data (for that department) is available in Redis Cache
#         - If present, return the specific subject data using the subject_id
#         - If not present in cache:
#           - Fetch the subject list from MongoDB where department matches
#           - Exclude unnecessary fields: created_at, updated_at
#           - Store the list of subjects efficiently in Redis Cache
#           - Return the requested subject's details from the fetched data

# Step 5: Return the subject data as the response

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

# Implementation Tip:
# - Consider keeping the data structure flexible so we can plug in these additional analytics easily
# - You can refer to `get_by_id()` in app/services/teacher_services/get_teachers_detail.py
# - It follows similar caching and DB fallbacks like `get_all_teachers()` in get_all_teachers.py

# Current focus: Implement Version 1.0 only, but keep it modular and scalable for 2.0 extension

@router.get("/subject/{subject_id}")
async def get_subject_by_id_route(
    subject_id: str = Path(..., description="Subject ID to fetch details for"),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
    return await get_subject_by_id(subject_id, user_data)


    