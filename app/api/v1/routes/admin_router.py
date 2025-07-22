from fastapi import APIRouter, Depends, Body,Path
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.services.admin_services.create_clerk import create_clerk
from app.services.admin_services.get_clerk import get_clerk,get_clerk_by_id
from app.middleware.is_logged_in import is_logged_in
from app.models.allModel import CreateClerkRequest

router = APIRouter()
security = HTTPBearer()  # Define security scheme

@router.post("/clerk/create")
async def create_clerk_route(
    request: CreateClerkRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
    
    return await create_clerk(request,user_data)


@router.get("/clerk/department/{department}")
async def get_subject(
    department: str = Path(..., description="Departement to fetch clerks for"),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
    return await get_clerk(department,user_data)



@router.get("/clerk/id/{email_id}")
async def get_subject_by_id_route(
    email_id: str = Path(..., description="Email ID"),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
    return await get_clerk_by_id(email_id, user_data)



# In this route we are deleting the clerk
# First check if role is admin or not
# Check if email id exist with role as clerk 
# If yes then delete the clerk , delete all the keys of redis where clerk data is present ( ex : clerk:yadavsuraj7449@gmail.com , clerk:BTECH)
# Also check if more keys are related to clerk then delete those as well
# Send a response that clerk is deleted successfully , about his account is deleted 
# Just add a message to the email qeueue that clerk account is deleted successfully

# # Ex :- # ✅ Send Delete Email Task to Queue
#         await send_to_queue("email_queue", {
#             "type": "send_email",
#             "data": {
#                 "to": student_data.email,
#                 "subject": "Welcome to MarkMe!",
#                 "body": f"Hello {student_data.first_name}, your registration is successful!"
#             }
#         }, priority=5)  # Medium priority for email

# To check the email queue you can need to run another process
# python -m app.worker.email_worker

# @router.put("/clerk/delete/{email_id}")
# async def delete_clerk_route(
#     email_id: str = Path(..., description="Email ID"),
#     credentials: HTTPAuthorizationCredentials = Depends(security),
#     user_data: dict = Depends(is_logged_in)
# ):
#     return await delete_clerk(email_id, user_data)




