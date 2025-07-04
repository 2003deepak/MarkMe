from fastapi import APIRouter, Form, UploadFile, File, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import ValidationError, BaseModel
from typing import List, Optional
from datetime import date
import json
from app.middleware.is_logged_in import is_logged_in

# -- Pydantic Model Import

router = APIRouter()
security = HTTPBearer()  # Define security scheme


# Pls refer to my code for updation and getting data for Student role 
# I except same logic for the teacher role as well

# In this route i want to get all data of teacher 
# First check the role of the user , proceed if teacher is there 
# Check if the teachers data is present in the Redis DB Cache , if present return it
# If not present , fetch it from the MongoDB and store it in the Redis Cache and also send it
# Pls exclude the field while fetching data from mongo db ( password, created_at, updated_at, password_reset_otp , password_reset_otp_expires ) 
# Dont save this fields in the Redis Cache as well

@router.get("/me")
# async def get_me(
#     credentials: HTTPAuthorizationCredentials = Depends(security),
#     user_data: dict = Depends(is_logged_in)
# ):
    
#     return await get_student_detail(user_data)


# In this route i want to update the profile of teacher
# It will be a form data request with the following fields
# first_name, middle_name, last_name, mobile_number, profile_picture
# First check the role of the user , proceed if teacher
# Update the profile in the MongoDB 
# As soon as data is updated in the MongoDB, delete the Redis Cache ( teacher key) for updated data storage
# Update the profile picture if provided, else keep it as it is 
# Upload the profile picture to the Image Kit IO and save the URL in the MongoDB


@router.put("/me/update-profile")
# async def update_profile(

#     first_name: Optional[str] = Form(None),
#     middle_name: Optional[str] = Form(None),
#     last_name: Optional[str] = Form(None),
#     mobile_number: Optional[str] = Form(None),
#     profile_picture: Optional[UploadFile] = File(None),
#     credentials: HTTPAuthorizationCredentials = Depends(security),
#     user_data: dict = Depends(is_logged_in)
# ):
#     
#     try:
#         # Create UpdateProfileRequest object from form data
#         update_request_data = UpdateProfileRequest(
#             first_name=first_name,
#             middle_name=middle_name,
#             last_name=last_name,
#             mobile_number=phone,
            
#         )

#         return await update_student_profile(
#             request_data=update_request_data,
#             user_data=user_data,
#             profile_picture=profile_picture
#         )
#     except ValidationError as e:
#         # Pydantic validation errors from UpdateProfileRequest
#         raise HTTPException(status_code=422, detail=json.loads(e.json()))
#     except HTTPException as e:
#         raise e
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")