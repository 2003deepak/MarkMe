from fastapi import APIRouter, Depends

router = APIRouter()


# Ask first name, middle_name , last name, email, mobile number, 6 digit pin ( generate random) , department
# Create a clerk account with the above details and send confirmation email to him 

# @router.post("/clerk/create")