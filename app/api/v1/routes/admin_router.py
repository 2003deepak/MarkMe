from fastapi import APIRouter, Depends
from app.services.admin import create_clerk
from fastapi import Body

router = APIRouter()


# Ask first name, middle_name , last name, email, mobile number, 6 digit pin ( generate random) , department
# Create a clerk account with the above details and send confirmation email to him 

@router.post("/clerk/create")
async def create_clerk_route(data: dict = Body(...)):
    return await create_clerk(data)