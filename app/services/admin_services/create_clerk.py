from fastapi import HTTPException, status
from app.core.database import get_db
from app.models.allModel import CreateClerkRequest
from passlib.context import CryptContext
from app.schemas.clerk import Clerk, ClerkRepository
from datetime import datetime
import random
from app.utils.send_email import send_email

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

async def create_clerk(request: CreateClerkRequest , user_data: dict):

    if user_data["role"] != "admin" :
        raise HTTPException(
                status_code=400,
                detail={
                    "status": "fail",
                    "message": "You Dont have right to create clerk"
                }
            )


    try:
        # Get database connection
        db = get_db()
        repo = ClerkRepository(db.client, db.name)

        # Check if clerk exists
        if await db.clerks.find_one({"email": request.email}):
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
        hashed_pin = pwd_context.hash(pin)

        # Create Clerk Pydantic model
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

        # Convert Clerk to dict before applying timestamps
        clerk_dict = clerk.dict()

        # Apply timestamps
        clerk_dict = await repo._apply_timestamps(clerk_dict)

        # Insert clerk into database
        await db.clerks.insert_one(clerk_dict)

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