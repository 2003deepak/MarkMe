from fastapi import APIRouter, Depends, Body
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.services.clerk_services.create_teacher import create_teacher
from app.services.clerk_services.create_subject import create_subject
from app.middleware.is_logged_in import is_logged_in

# --- Pydantic Imports
from app.models.allModel import CreateSubjectRequest, TeacherRegisterRequest

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