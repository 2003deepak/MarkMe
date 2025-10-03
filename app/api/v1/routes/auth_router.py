from fastapi import APIRouter, Depends, Request
from app.services.auth_services.auth import login_user, refresh_access_token, request_password_reset, reset_user_password,change_current_password,verify_reset_otp

# --- Pydantics Model Import ----- 
from app.models.allModel import LoginRequest , ForgotPasswordRequest,ResetPasswordRequest,ChangePasswordRequest,OtpRequest,RefreshTokenRequest

router = APIRouter()



@router.post("/login")
async def login(request : LoginRequest):
    return await login_user(request)

@router.post("/refresh-token")
async def apply_refresh_access_token(
    request: Request  
):
    return await refresh_access_token(request)

@router.post("/logout")
async def logout():
    return {"status": "success", "message": "Logout successful"}


@router.post("/forgot-password")
async def forgot_password(request: ForgotPasswordRequest):
    return await request_password_reset(request)

@router.post("/verify-otp")
async def forgot_password(request: OtpRequest):
    return await verify_reset_otp(request)


@router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest):
    return await reset_user_password(request)



@router.put("/change-password")
async def change_password_route(
    request_model: ChangePasswordRequest,
    request: Request  
):
    return await change_current_password(request_model,request)