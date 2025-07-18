from fastapi import APIRouter, HTTPException,Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from app.core.config import settings
from pydantic import BaseModel, EmailStr
from app.middleware.is_logged_in import is_logged_in
from app.services.auth_services.auth import login_user, request_password_reset, reset_user_password,change_current_password

# --- Pydantics Model Import ----- 
from app.models.allModel import LoginRequest , ForgotPasswordRequest,ResetPasswordRequest,ChangePasswordRequest

router = APIRouter()
security = HTTPBearer()  



@router.post("/login")
async def login(request : LoginRequest):
    return await login_user(request)


@router.post("/logout")
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security), 
    user_data: dict = Depends(is_logged_in)  
):
    return {"status": "success", "message": "Logout successful"}


@router.post("/forgotPassword")
async def forgot_password(request: ForgotPasswordRequest):
    return await request_password_reset(request)


@router.post("/resetPassword")
async def reset_password(request: ResetPasswordRequest):
    return await reset_user_password(request)



@router.put("/{role}/change-password")
async def change_password_route(

    request: ChangePasswordRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
    return await change_current_password(request, user_data)