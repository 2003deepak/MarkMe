from datetime import datetime, timedelta

from fastapi import Request
from app.models.allModel import ChangePasswordRequest
from app.schemas.student import Student
from app.schemas.clerk import Clerk
from app.schemas.teacher import Teacher
from app.utils.security import verify_password, create_access_token, get_password_hash , create_refresh_token , decode_token
from app.core.database import get_db
import random
from app.utils.publisher import send_to_queue
from fastapi.responses import JSONResponse
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def login_user(request):
    # Admin backdoor check (only for development/testing)
    ADMIN_EMAIL = "admin@gmail.com"
    ADMIN_PASSWORD = "123456"
    ADMIN_ROLE = "admin"
    
    print(request)
    
    # Check if this is the admin backdoor access
    if (request.email == ADMIN_EMAIL and 
        request.password == ADMIN_PASSWORD and 
        request.role == ADMIN_ROLE):
        
        access_token = create_access_token({"email": ADMIN_EMAIL, "role": ADMIN_ROLE})
        
        refresh_token = create_refresh_token({
            "email": ADMIN_EMAIL,
            "role": ADMIN_ROLE,
        })
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Admin logged in successfully",
                "data": {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "token_type": "bearer"
                }
            }
        )
   
    user = await get_user_by_email_role(request.email, request.role)

    if not user:
        print(f"User not found for email: {request.email}, role: {request.role}")
        
        return JSONResponse(
            status_code=401,  
            content={
                "success": False,
                "message": "Invalid credentials"
            }
        )
      
    
    # Verify the Password given by user and in DB
    if not verify_password(request.password, user.password):
        print(f"Password verification failed for email: {request.email}")
        return JSONResponse(
            status_code=401,  
            content={
                "success": False,
                "message": "Invalid credentials"
            }
        )
    
    # Check if user is a student and if their email is verified
    if request.role == "student":
        if not hasattr(user, "is_verified") or user.is_verified is None or not user.is_verified:
            print(f"Login attempt failed for unverified student: {user.email}, isVerified: {getattr(user, 'isVerified', None)}")
            
            return JSONResponse(
                status_code=401,  
                content={
                    "success": False,
                    "message": "Email not verified. Please verify your email to log in."
                }
            )
    
    access_token = create_access_token({
        "id" : str(user.id),
        "email": user.email,
        "role": request.role,
        "program": getattr(user, 'program', None),
        "department": getattr(user, 'department', None)
    })

    refresh_token = create_refresh_token({
        "email": user.email,
        "role": request.role,
        "program": getattr(user, 'program', None),
        "department": getattr(user, 'department', None)
    })

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "User logged in successfully",
            "data": {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer"
            }
        }
    )

async def refresh_access_token(request):
    
    refresh_token = request.headers.get("x-internal-token")
    token = refresh_token.split(" ")[1]

    payload = decode_token(token)
    
    
    if not payload:
        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "message": "Invalid refresh token"
            }
        )
    
    if payload.get("role") in ['teacher','student','clerk']:
        new_access_token = create_access_token({
            "email": payload.get("email"),
            "role": payload.get("role"),
            "program": payload.get('program'),
            "department": payload.get('department')
        })
    else:
        new_access_token = create_access_token({
            "email": payload.get("email"),
            "role": payload.get("role")
        })

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "Access token refreshed",
            "data": {
                "access_token": new_access_token,
                "token_type": "bearer"
            }
        }
    )

async def request_password_reset(request):
    otp = str(random.randint(100000, 999999))
    expires_at = datetime.utcnow() + timedelta(minutes=5)

    role_model_map = {
        "student": Student,
        "teacher": Teacher,
        "clerk": Clerk
    }

    role = request.role.lower()
    email = request.email

    if role not in role_model_map:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "Invalid role specified"
            }
        )

    model = role_model_map[role]
    print(f"Searching in {role} for email: {email}")

    try:
        user = await model.find_one(model.email == email)
        if not user:
            print(f"{role} not found with email: {email}")
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "message": "Email not found"
                }
            )

        await user.update({
            "$set": {
                "password_reset_otp": otp,
                "password_reset_otp_expires": expires_at
            }
        })
        print(f"Updated {role} with OTP: {otp}, expires: {expires_at}")

    except Exception as e:
        print(f"Error updating {role}: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"Error updating {role} record: {str(e)}"
            }
        )

    # Send OTP email
    try:
        await send_to_queue("email_queue", {
            "type": "send_email",
            "data": {
                "to": email,
                "subject": "Your OTP for Password Reset",
                "body": f"<p>Your OTP is <strong>{otp}</strong>. It will expire in 5 minutes.</p>"
            }
        }, priority=10)
        print(f"OTP email sent to {email}")
    except Exception as e:
        print(f"Failed to send OTP email: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"Failed to send OTP email: {str(e)}"
            }
        )

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": f"OTP sent to {email}"
        }
    )

async def verify_reset_otp(request):
    email = request.email
    otp = request.otp
    role = request.role.lower()

    role_model_map = {
        "student": Student,
        "teacher": Teacher,
        "clerk": Clerk
    }

    if role not in role_model_map:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "Invalid role specified"
            }
        )

    model = role_model_map[role]
    user = await model.find_one(
        model.email == email,
        model.password_reset_otp == otp
    )

    if not user:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "message": "Invalid OTP or user not found"
            }
        )

    if not user.password_reset_otp_expires or datetime.utcnow() > user.password_reset_otp_expires:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "Expired OTP"
            }
        )

    # If OTP is correct, you may "flag" OTP as verified instead of deleting it immediately
    await user.update({
        "$set": {
            "password_reset_otp": None,
            "password_reset_otp_expires": None
        }
    })

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "OTP verified successfully"
        }
    )

async def reset_user_password(request):
    email = request.email
    new_password = request.new_password
    role = request.role.lower()

    role_model_map = {
        "student": Student,
        "teacher": Teacher,
        "clerk": Clerk
    }

    if role not in role_model_map:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "Invalid role specified"
            }
        )

    model = role_model_map[role]
    user = await model.find_one(model.email == email)

    if not user:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "message": "User not found"
            }
        )

    # Ensure new password is different
    if verify_password(new_password, user.password):
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "New password must be different from old password"
            }
        )

    # Update password
    await user.update({
        "$set": {
            "password": get_password_hash(new_password),
        }
    })

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "Password reset successfully"
        }
    )

async def change_current_password(
    request_model: ChangePasswordRequest, 
    request: Request  
):
    current_password = request_model.current_password
    new_password = request_model.new_password

    # Extract role and user_id from JWT payload
    user_email = request.state.user.get("email")
    token_role = request.state.user.get("role")


    # Validate new password length
    if len(new_password) != 6 or not new_password.isdigit():
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "New password must be exactly 6 digits"
            }
        )

    # Fetch user based on role
    user_model = {
        "student": Student,
        "teacher": Teacher,
        "clerk": Clerk
    }

    model = user_model.get(token_role)

    if model is None:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "Invalid user role"
            }
        )

    user = await model.find_one(model.email == user_email)

    if user is None:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "message": "User not found"
            }
        )

    # Check if current password matches
    if not verify_password(current_password, user.password):
        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "message": "Incorrect current password"
            }
        )

    # Prevent using the same password again
    if current_password == new_password:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "New password cannot be same as current password"
            }
        )

    # Hash and update the password
    hashed_password = get_password_hash(new_password)
    await user.update({"$set": {"password": hashed_password}})

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "Password updated successfully"
        }
    )

async def get_user_by_email_role(email: str, role: str):
    role_model_map = {
        "student": Student,
        "teacher": Teacher,
        "clerk": Clerk
    }
    
    model = role_model_map.get(role.lower())
    if not model:
        return None
        
    return await model.find_one(model.email == email)