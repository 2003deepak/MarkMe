from fastapi import HTTPException
from datetime import datetime, timedelta
from app.schemas.student import Student
from app.schemas.clerk import Clerk
from app.schemas.teacher import Teacher
from typing import Optional
from app.utils.security import verify_password , create_access_token , get_password_hash
from app.core.database import get_db
import random
from app.utils.publisher import send_to_queue


async def login_user(request):

    # Admin backdoor check (only for development/testing)
    ADMIN_EMAIL = "admin@gmail.com"
    ADMIN_PASSWORD = "123456"
    ADMIN_ROLE = "admin"
    
    # Check if this is the admin backdoor access
    if (request.email == ADMIN_EMAIL and 
        request.password == ADMIN_PASSWORD and 
        request.role == ADMIN_ROLE):
        
        access_token = create_access_token({"email": ADMIN_EMAIL, "role": ADMIN_ROLE})
        return {
            "status": "success",
            "message": "Admin logged in successfully",
            "data": {
                "access_token": access_token,
                "token_type": "bearer"
            }
        }
   
    user = await get_user_by_email_role(request.email, request.role)

    if not user :
        raise HTTPException(
            status_code=401,
            detail={
                "status": "fail",
                "message": "Invalid credentials"
            }
        )
    
    # Verify the Password given by user and in DB

    if not verify_password(request.password, user["password"]) :
        raise HTTPException(
            status_code=401,
            detail={
                "status": "fail",
                "message": "Invalid credentials"
            }
        )

    
    access_token = create_access_token({"email": user["email"] , "role": request.role})

    return {
        "status": "success",
        "message": "User logged in successfully",
        "data": {
            "access_token": access_token,
            "token_type": "bearer"
        }
    }


async def request_password_reset(request):
    db = get_db()

    otp = str(random.randint(100000, 999999))
    expires_at = datetime.utcnow() + timedelta(minutes=5)

    # Check and update in a single step across collections
    role_collection_map = {
        "student": db.students,
        "teacher": db.teachers,
        "clerk": db.clerks
    }

    updated = False
    for collection in role_collection_map.values():
        result = await collection.update_one(
            {"email": request.email},
            {"$set": {
                "password_reset_otp": otp,
                "password_reset_otp_expires": expires_at
            }}
        )
        if result.modified_count > 0:
            updated = True
            break

    if not updated:
        raise HTTPException(
            status_code=404,
            detail={"status": "fail", "message": "Email not registered with us"}
        )

    # send email to registered mail
    await send_to_queue("email_queue", {
            "type": "send_email",
            "data": {
                "to": request.email,
                "subject": "Your OTP for Password Reset",
                "body": f"<p>Your OTP is <strong>{otp}</strong>. It will expire in 5 minutes.</p>"
            }
        }, priority=10)  # High priority for email

    
    

    return {
        "status": "success",
        "message": f"OTP sent to {request.email}"
    }


async def reset_user_password(request):

    db = get_db()
    email = request.email
    otp = request.otp
    new_password = request.new_password

    updated = False

    role_collection_map = {
        "student": db.students,
        "teacher": db.teachers,
        "clerk": db.clerks
    }

    for collection in role_collection_map.values():
        # 1. Find user by email and OTP
        user = await collection.find_one({
            "email": email,
            "password_reset_otp": otp
        })

        if user:
            # 2. Check if OTP is expired
            if (
                "password_reset_otp_expires" not in user or 
                user["password_reset_otp_expires"] is None or 
                datetime.utcnow() > user["password_reset_otp_expires"]
            ):
                raise HTTPException(
                    status_code=400,
                    detail={"status": "fail", "message": "Expired OTP"}
                )

            # 3. Ensure new password is different
            if verify_password(new_password, user["password"]):
                raise HTTPException(
                    status_code=400,
                    detail={"status": "fail", "message": "New password must be different from old password"}
                )

            # 4. Update password and set OTP fields to null
            await collection.update_one(
                {"_id": user["_id"]},
                {
                    "$set": {
                        "password": get_password_hash(new_password),
                        "password_reset_otp": None,
                        "password_reset_otp_expires": None
                    }
                }
            )

            updated = True
            break

    if not updated:
        raise HTTPException(
            status_code=404,
            detail={"status": "fail", "message": "Invalid OTP or user not found"}
        )

    return {
        "status": "success",
        "message": "Password reset successfully"
    }


async def change_current_password(request, user_data):
    db = get_db()
    current_password = request.current_password
    new_password = request.new_password
    request_email = request.email

    # Extract role and user_id from JWT payload
    user_email = user_data["email"]
    token_role = user_data["role"].lower()

    # Validate if role from token matches the role in request path
    if request_email != user_email:
        raise HTTPException(
            status_code=403,
            detail={"status": "fail", "message": "You are not authorized to change others' password"},
        )

    # Validate new password length
    if len(new_password) != 6 or not new_password.isdigit():
        raise HTTPException(
            status_code=400,
            detail={"status": "fail", "message": "New password must be exactly 6 digits"},
        )

    # Fetch user based on role
    user_model = {
        "student": db.students,
        "teacher": db.teachers,
        "clerk": db.clerks
    }

    collection = user_model.get(token_role)

    if collection is None:
        raise HTTPException(
            status_code=400,
            detail={"status": "fail", "message": "Invalid user role"},
        )

    user = await collection.find_one({"email": user_email})

    if user is None:
        raise HTTPException(
            status_code=404,
            detail={"status": "fail", "message": "User not found"},
        )

    # Check if current password matches
    if not verify_password(current_password, user["password"]):  # use user["password"] since it's a dict
        raise HTTPException(
            status_code=401,
            detail={"status": "fail", "message": "Incorrect current password"},
        )

    # Prevent using the same password again
    if current_password == new_password:
        raise HTTPException(
            status_code=400,
            detail={"status": "fail", "message": "New password cannot be same as current password"},
        )

    # Hash and update the password
    hashed_password = get_password_hash(new_password)
    await collection.update_one({"email": user_email}, {"$set": {"password": hashed_password}})

    return {"status": "success", "message": "Password updated successfully"}


async def get_user_by_email_role(email: str, role: str) -> Optional[dict]:
    db = get_db() 

    if role.lower() == "student":
        return await db.students.find_one({"email": email})
    elif role.lower() == "teacher":
        return await db.teachers.find_one({"email": email})
    elif role.lower() == "clerk":
        return await db.clerks.find_one({"email": email})
    # elif role.lower() == "admin":
    #     return await db.admins.find_one({"email": email})
    else:
        return None
