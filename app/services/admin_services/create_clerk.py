from fastapi import HTTPException, status
from app.core.database import get_db
from app.models.allModel import CreateClerkRequest
from passlib.context import CryptContext
from app.utils.security import get_password_hash
from app.schemas.clerk import Clerk
from datetime import datetime
import random
from app.utils.send_email import send_email

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

async def create_clerk(request: CreateClerkRequest, user_data: dict):
    if user_data["role"] != "admin":
        raise HTTPException(
            status_code=400,
            detail={
                "status": "fail",
                "message": "You don't have right to create clerk"
            }
        )

    try:
        # Check if clerk exists
        if await Clerk.find_one(Clerk.email == request.email):
            raise HTTPException(
                status_code=400,
                detail={
                    "status": "fail",
                    "message": "Clerk already exists"
                }
            )

        # Generate random 6-digit PIN
        pin = str(random.randint(100000, 999999))

        # Hash the PIN
        hashed_pin = get_password_hash(str(pin))


        # Create Clerk Beanie model
        clerk = Clerk(
            first_name=request.first_name,
            middle_name=request.middle_name,
            last_name=request.last_name,
            email=request.email,
            password=hashed_pin,
            department=request.department,
            program=request.program,
            phone=request.mobile_number,
        )

        # Save clerk to database (timestamps are handled by Beanie's pre_save)
        await clerk.save()

        # Send confirmation email
        try:
            await send_email(
                subject="Your Clerk Account PIN",
                email_to=request.email,
                body=f"<p>Welcome, {request.first_name}!<br>Your login PIN is <strong>{pin}</strong>.</p>"
            )
        except Exception as e:
            print(f"Failed to send email to {request.email}: {str(e)}")

        return {
            "status": "success",
            "message": "Clerk created successfully",
            "data": {
                "name": f"{request.first_name} {request.last_name}",
                "email": request.email,
                "department": request.department
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Clerk creation error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={
                "status": "fail",
                "message": f"Error creating clerk: {str(e)}"
            }
        )