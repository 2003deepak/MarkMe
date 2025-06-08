from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.core.config import settings

router = APIRouter()


# User logins to the system , whether it is a student/admin/teacher/clerk 
# Take email and password and role as input
# If sucessful, return a token and json response 
# I want JSON response to be like this: 
# { status: 'fail', message: 'Invalid Username or Password' }
# { status: 'success', message: 'User logged in successfully', data : "any data to send back"}


# @router.post("/login")


# Ask user for his regsitered email address/Mobile Numer
# If email or mobile number is not registered, return a message saying "Email or Mobile Number not registered"
# If registered, send a 6-digit OTP to the email or mobile number
# Save the OTP in the database with an expiry time of 5 minutes

# @router.post("/forgotPassword")



# Ask user for the OTP sent to his email or mobile number
# If OTP is correct, allow user to reset password
# Ask for new 6 digit pin 
# save the new pin in the database

# @router.post("/resetPassword")
