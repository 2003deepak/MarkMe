from datetime import datetime, timedelta

from beanie import Link
from bson import ObjectId
from fastapi import Request
from app.models.allModel import ChangePasswordRequest
from app.schemas.fcm import FCMToken
from app.schemas.student import Student
from app.schemas.clerk import Clerk
from app.schemas.teacher import Teacher
from app.utils.security import verify_password, create_access_token, get_password_hash , create_refresh_token , decode_token
import random
from app.utils.publisher import send_to_queue
from fastapi.responses import JSONResponse
import logging
from app.utils.send_otp import generate_and_store_otp, verify_otp
from app.core.redis import redis_client

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def login_user(request):

    # ---------------- ADMIN BACKDOOR ----------------
    ADMIN_EMAIL = "admin@gmail.com"
    ADMIN_PASSWORD = "123456"
    ADMIN_ROLE = "admin"

    if (
        request.email == ADMIN_EMAIL and
        request.password == ADMIN_PASSWORD and
        request.role == ADMIN_ROLE
    ):
        access_token = create_access_token({
            "email": ADMIN_EMAIL,
            "role": ADMIN_ROLE
        })
        refresh_token = create_refresh_token({
            "email": ADMIN_EMAIL,
            "role": ADMIN_ROLE
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

    # ---------------- LOAD USER ----------------
    user = await get_user_by_email_role(request.email, request.role)

    if not user or not verify_password(request.password, user.password):
        return JSONResponse(
            status_code=401,
            content={"success": False, "message": "Invalid credentials"}
        )

    if request.role == "student" and not user.is_verified:
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Email not verified"}
        )

    # ---------------- ROLE BASED PAYLOAD ----------------
    if request.role == "student":
        access_payload = {
            "id": str(user.id),
            "email": user.email,
            "role": "student",
            "roll_number": user.roll_number,
            "program": user.program,
            "department": user.department,
            "semester": user.semester,
            "batch_year": user.batch_year
        }

    elif request.role in ["teacher", "clerk"]:
        access_payload = {
            "id": str(user.id),
            "email": user.email,
            "role": request.role,
            "department": user.department
        }

    else:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Invalid role"}
        )

    access_token = create_access_token(access_payload)

    # Refresh token 
    refresh_token = create_refresh_token({
        "id": str(user.id),
        "email": user.email,
        "role": request.role
    })

    # ---------------- FCM TOKEN ----------------
    if request.fcm_token:
        existing = await FCMToken.find_one({"token": request.fcm_token})

        if existing:
            await existing.update({
                "$set": {
                    "user_id": user.id,
                    "user_role": request.role,
                    "device_type": request.device_type,
                    "device_info": request.device_info,
                    "active": True,
                    "last_used_at": datetime.utcnow()
                }
            })
        else:
            await FCMToken(
                user_id=user.id,
                user_role=request.role,
                token=request.fcm_token,
                device_type=request.device_type,
                device_info=request.device_info,
                active=True,
                created_at=datetime.utcnow(),
                last_used_at=datetime.utcnow()
            ).insert()

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

  
async def logout_user(request,request_model):

    user_id = request.state.user.get("id")
    fcm_token = request_model.fcm_token

    if not fcm_token:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "FCM token required"},
        )

    record = await FCMToken.find_one(
        {"user_id": ObjectId(user_id), "token": fcm_token}
    )

    if not record:
        print("No user found with fcm token =  " , fcm_token)
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "message": "FCM token not found or does not belong to user",
            },
        )

    await record.delete()

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "Logged out successfully",
        },
    )
  

from fastapi import Request
from fastapi.responses import JSONResponse
from bson import ObjectId

from app.schemas.student import Student
from app.schemas.teacher import Teacher
from app.schemas.clerk import Clerk
from app.utils.security import decode_token, create_access_token


async def refresh_access_token(request: Request):

    # ---------------- READ REFRESH TOKEN ----------------
    auth_header = request.headers.get("x-internal-token")
    if not auth_header:
        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "message": "Refresh token missing"
            }
        )

    # Expecting: "Bearer <token>"
    try:
        token = auth_header.split(" ")[1]
    except IndexError:
        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "message": "Invalid refresh token format"
            }
        )

    payload = decode_token(token)
    if not payload:
        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "message": "Invalid or expired refresh token"
            }
        )

    role = payload.get("role")
    email = payload.get("email")
    user_id = payload.get("id")

    # ---------------- ADMIN (NO DB LOOKUP) ----------------
    if role == "admin":
        new_access_token = create_access_token({
            "email": email,
            "role": "admin"
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

    # ---------------- ROLE → MODEL MAP ----------------
    role_model_map = {
        "student": Student,
        "teacher": Teacher,
        "clerk": Clerk
    }

    model = role_model_map.get(role)
    if not model:
        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "message": "Invalid role in refresh token"
            }
        )

    if not user_id:
        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "message": "User ID missing in refresh token"
            }
        )

    # ---------------- FETCH USER FROM DB ----------------
    user = await model.find_one(model.id == ObjectId(user_id))
    if not user:
        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "message": "User no longer exists"
            }
        )

    # ---------------- BUILD NEW ACCESS TOKEN ----------------
    if role == "student":
        access_payload = {
            "id": str(user.id),
            "email": user.email,
            "role": "student",
            "roll_number": user.roll_number,
            "program": user.program,
            "department": user.department,
            "semester": user.semester,
            "batch_year": user.batch_year
        }
    else:
        access_payload = {
            "id": str(user.id),
            "email": user.email,
            "role": role,
            "department": user.department
        }

    new_access_token = create_access_token(access_payload)

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

    # Generate and store OTP in Redis
    try:
        otp = await generate_and_store_otp(email)
    except ValueError as e:
        return JSONResponse(
            status_code=429,
            content={
                "success": False,
                "message": str(e)
            }
        )

    # Send OTP email
    try:
        await send_to_queue("email_queue", {
            "type": "send_email",
            "data": {
                "to": email,
                "subject": "Your OTP for Password Reset",
                "body": f"<p>Your OTP is <strong>{otp}</strong>. It will expire in 10 minutes.</p>"
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
    
    # Verify OTP using utility
    is_valid, message = await verify_otp(email, otp)

    if not is_valid:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": message
            }
        )

    # Set verification flag in Redis for 10 minutes
    await redis_client.setex(f"reset_verified:{email}", 600, "1")

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

    # Check if user is verified via Redis
    is_verified = await redis_client.get(f"reset_verified:{email}")
    if not is_verified:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "Email not verified or verification expired. Please verify OTP again."
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
    
    # Clean up verification flag
    await redis_client.delete(f"reset_verified:{email}")

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
            status_code=404,
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