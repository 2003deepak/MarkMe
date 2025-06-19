from fastapi import APIRouter, Depends, Body
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.services.admin_services.create_clerk import create_clerk
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