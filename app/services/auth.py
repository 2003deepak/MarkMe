from fastapi import HTTPException
from datetime import datetime, timedelta
from app.core.security import create_access_token, verify_password, get_password_hash
import random
from app.services.user_services import get_user_by_email_role
from app.schemas.otp import OTP
from app.core.mail_config import send_email


async def login_user(payload):
    email = payload.email
    password = payload.password
    role = payload.role

    user = await get_user_by_email_role(email, role)
    if not user or not verify_password(password, user.password):
        raise HTTPException(
            status_code=401,
            detail={
                "status": "fail",
                "message": "Invalid credentials"
            }
        )

    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(
        data={"sub": user.email},
        expires_delta=access_token_expires
    )

    return {
        "status": "success",
        "message": "User logged in successfully",
        "data": {
            "access_token": access_token,
            "token_type": "bearer"
        }
    }


async def send_otp(email_or_phone: str):
    # Search across all user roles
    user_found = False
    for role in ["student", "teacher", "clerk"]:
        user = await get_user_by_email_role(email_or_phone, role)
        if user:
            user_found = True
            break

    if not user_found:
        raise HTTPException(
            status_code=404,
            detail={
                "status": "fail",
                "message": "Email or Mobile Number not registered"
            }
        )

    otp = str(random.randint(100000, 999999))
    expires_at = datetime.utcnow() + timedelta(minutes=5)

    await OTP(
        email_or_phone=email_or_phone,
        otp=otp,
        expires_at=expires_at
    ).insert()

    await send_email(
        subject="Your OTP for Login",
        email_to=email_or_phone,
        body=f"<p>Your OTP is <strong>{otp}</strong>. It will expire in 5 minutes.</p>"
    )

    return {
        "status": "success",
        "message": f"OTP sent to {email_or_phone}"
    }


async def reset_user_password(email_or_phone: str, otp: str, new_password: str):
    record = await OTP.find_one(
        OTP.email_or_phone == email_or_phone,
        OTP.otp == otp
    )

    if not record or datetime.utcnow() > record.expires_at:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "fail",
                "message": "Invalid or expired OTP"
            }
        )

    user = None
    for role in ["student", "teacher", "clerk"]:
        user = await get_user_by_email_role(email_or_phone, role)
        if user:
            user.password = get_password_hash(new_password)
            await user.save()
            break

    if not user:
        raise HTTPException(
            status_code=404,
            detail={
                "status": "fail",
                "message": "User not found"
            }
        )

    await record.delete()

    return {
        "status": "success",
        "message": "Password reset successfully"
    }
