from fastapi import APIRouter, Depends, Body,Path
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.services.admin_services.create_clerk import create_clerk
from app.services.admin_services.get_clerk import get_clerk,get_clerk_by_id
from app.services.admin_services.delete_clerk import delete_clerk
from app.middleware.is_logged_in import is_logged_in
from app.models.allModel import CreateClerkRequest

router = APIRouter()
security = HTTPBearer()  # Define security scheme

@router.post("/clerk/create")
async def create_clerk_route(   
    request: CreateClerkRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
    
    return await create_clerk(request,user_data)


@router.get("/clerk/department/{department}")
async def get_subject(
    department: str = Path(..., description="Departement to fetch clerks for"),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
    return await get_clerk(department,user_data)



@router.get("/clerk/{email_id}")
async def get_subject_by_id_route(
    email_id: str = Path(..., description="Email ID"),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
    return await get_clerk_by_id(email_id, user_data)



@router.put("/clerk/delete/{email_id}")
async def delete_clerk_route(
    email_id: str = Path(..., description="Email ID"),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
    return await delete_clerk(email_id, user_data)




