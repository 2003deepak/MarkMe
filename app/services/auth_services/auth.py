from fastapi import HTTPException
from datetime import datetime, timedelta
from app.schemas.student import Student
from app.schemas.clerk import Clerk
from app.schemas.teacher import Teacher
from typing import Optional
from app.utils.security import verify_password , create_access_token , get_password_hash
from app.core.database import get_db
import random
from app.schemas.otp import OTP
from app.utils.send_email import send_email


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

    await send_email(
        subject="Your OTP for Password Reset",
        email_to=request.email,
        body=f"<p>Your OTP is <strong>{otp}</strong>. It will expire in 5 minutes.</p>"
    )
    

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
