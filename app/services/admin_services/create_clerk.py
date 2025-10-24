from fastapi import HTTPException
from fastapi.responses import JSONResponse
from app.core.database import get_db
from app.models.allModel import CreateClerkRequest
from passlib.context import CryptContext
from app.utils.security import get_password_hash
from app.core.redis import redis_client
from app.schemas.clerk import Clerk
import random
from app.utils.publisher import send_to_queue  

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

async def create_clerk(request,request_model: CreateClerkRequest):
    
    
    if request.state.user.get("role") != "admin":
        
        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "message": "You don't have right to create clerk"
            }
        )

    try:
        # Check if clerk exists
        if await Clerk.find_one(Clerk.email == request_model.email):
          
            return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "Clerk already exists"
            }
        )
            
            

        # Generate random 6-digit PIN
        pin = str(random.randint(100000, 999999))

        # Hash the PIN
        hashed_pin = get_password_hash(str(pin))


        # Create Clerk Beanie model
        clerk = Clerk(
            first_name=request_model.first_name,
            middle_name=request_model.middle_name,
            last_name=request_model.last_name,
            email=request_model.email,
            password=hashed_pin,
            department=request_model.department,
            program=request_model.program,
            phone=request_model.mobile_number,
        )

        # Save clerk to database (timestamps are handled by Beanie's pre_save)
        await clerk.save()

        # Delete Redis Key
        cache_key = f"clerks:{request_model.department}"
        await redis_client.delete(cache_key)


        # Send confirmation email

        # ✅ Send Welcome Email Task to Queue
        await send_to_queue("email_queue", {
            "type": "send_email",
            "data": {
                "to": request_model.email,
                "subject": "Welcome to MarkMe!",
                "body": f"Hello {request_model.first_name}, your registration is successfull as role of Clerk Your login PIN is <strong>{pin}</strong>.</p>"
            }
        }, priority=5) # Medium priority for email
        
        return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "Clerk created successfully",
            "data": {
                "name": f"{request_model.first_name} {request_model.last_name}",
                "email": request_model.email,
                "department": request_model.department
            }
        }
    )
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"Clerk creation error: {str(e)}")
        
        return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": f"Error creating clerk: {str(e)}"
           
        }
        )