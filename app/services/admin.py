from fastapi import HTTPException
import random
from app.core.security import get_password_hash
from app.schemas.clerk import Clerk
from app.schemas.otp import OTP
from app.core.mail_config import send_email


async def create_clerk(data: dict):
    required_fields = ["first_name", "last_name", "email", "phone", "department"]
    for field in required_fields:
        if field not in data:
            raise HTTPException(
                status_code=400,
                detail={
                    "status": "fail",
                    "message": f"Missing field: {field}"
                }
            )

    pin = str(random.randint(100000, 999999))
    data['password'] = pin
    clerk = Clerk(**data)
    await clerk.insert()

    await send_email(
        subject="Your Clerk Account PIN",
        email_to=data["email"],
        body=f"<p>Welcome, Clerk!<br>Your login PIN is <strong>{pin}</strong>.</p>"
    )

    return {
        "status": "success",
        "message": "Clerk account created successfully",
        "data": {"generated_pin": pin}
    }
