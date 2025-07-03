from fastapi import APIRouter, Depends, Body
from app.schemas.timetable import Timetable
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.services.clerk_services.create_teacher import create_teacher
from app.services.clerk_services.create_subject import create_subject
from app.services.clerk_services.add_timetable import add_timetable
from app.middleware.is_logged_in import is_logged_in

# --- Pydantic Imports
from app.models.allModel import CreateSubjectRequest, TeacherRegisterRequest

router = APIRouter()
security = HTTPBearer()  # Define security scheme

@router.post("/subject/create")
async def create_subject_route(
    request: CreateSubjectRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
    
    return await create_subject(request,user_data)

@router.post("/teacher/create")
async def create_teacher_route(
    request: TeacherRegisterRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
   
    return await create_teacher(request,user_data)



# In this route , i want that clerk can create a timetable for a specific program and specific semester
# In the function , validate that current role is clerk and then proceed to create the timetable
# The request should academic_year,department,program,semester,class_name and schedule ( List of Session ( Pydantic Model) )

# The Session Pydantic Model should have the following fields: start_time, end_time, subject, teacher (_id) , room ( _id) 

# Expected JSON structure :- 

# {
#   "academicYear": "2024",
#   "department": "BTECH",
#   "program": "MCA",
#   "semester": "1",
#   "schedule": {
#     "Monday": [
#       {
#         "startTime": "09:00",
#         "endTime": "10:30",
#         "subject": "507f1f77bcf86cd799439011", // Math ID
#         "teacher": "507f1f77bcf86cd799439012"  // Prof. X ID
#       },
#       // More sessions...
#     ],
#     // Other days...
#   }
# }



@router.post("/timetable/create")
async def create_timetable(
    request: Timetable,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
    
    return await add_timetable(request,user_data)

   
    