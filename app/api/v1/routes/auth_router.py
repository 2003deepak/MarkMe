from fastapi import APIRouter, HTTPException,Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from app.core.config import settings
from pydantic import BaseModel, EmailStr
from app.middleware.is_logged_in import is_logged_in
from app.services.auth_services.auth import login_user, request_password_reset, reset_user_password

# --- Pydantics Model Import ----- 
from app.models.allModel import LoginRequest , ForgotPasswordRequest,ResetPasswordRequest

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


# In this code , pls note that it is for student,clerk,teacher to change thier existing password
# The function should expect :- 

# 1) The current password of the user
# 2) The new password that the user wants to set
# 3) The user role (student, clerk, teacher)

# When the user make a request for password change , since this is a protected route, the user must be logged in 
# and the request will have a valid JWT token from the variable user_data
# So the current user role that will be extracted from the user_data variable
# Match the user role with the request role and then proceed to change the password
# Properly handle the case where the user tries to change the password for a different role
# Properly validate new password length should be exact 6 digtts and should not be same as the current password


# @router.put("/{role}/change-password")
# async def change_password_route(

#     request: ChangePasswordRequest,
#     credentials: HTTPAuthorizationCredentials = Depends(security),
#     user_data: dict = Depends(is_logged_in)
# ):
#     return await change_currenr_password(request, user_data)