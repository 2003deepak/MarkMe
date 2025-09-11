from fastapi import APIRouter, Depends, Body,Path
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.services.clerk_services.create_teacher import create_teacher
from app.services.clerk_services.create_subject import create_subject
from app.middleware.is_logged_in import is_logged_in
from app.services.teacher_services.get_all_teachers import get_all_teachers
from app.services.teacher_services.get_teacher_detail import get_teacher_by_id
from app.services.clerk_services.add_timetable import add_timetable
from app.services.clerk_services.get_subject_detail import get_subject_detail,get_subject_by_id
from app.models.allModel import ClassSearchRequest


# --- Pydantic Imports
from app.models.allModel import CreateSubjectRequest, TeacherRegisterRequest , TimeTableRequest

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


@router.get("/teacher")
async def get_all_teachers_route(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
    return await get_all_teachers(user_data)



@router.get("/teacher/{teacher_id}")
async def get_teacher_route(
    teacher_id: str = Path(..., description="Teacher ID to fetch details for"),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
    return await get_teacher_by_id(teacher_id, user_data)


@router.get("/subject")
async def get_subject(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
    return await get_subject_detail(user_data)


@router.get("/subject/{subject_id}")
async def get_subject_by_id_route(
    subject_id: str = Path(..., description="Subject ID to fetch details for"),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
    return await get_subject_by_id(subject_id, user_data)



# This Route is used to update the data of the Clerk
#     
#     Steps:
#     1. Check if `user_data["role"] == "clerk"`.
#     2. Fields to update (if provided in request body):
#         - first_name
#         - middle_name
#         - last_name
#         - phone
#         - profile_picture (ask from user if they want to update)
#     3. Update the data in DB properly.
#     4. Delete Redis keys where old data for this clerk can exist.
#        - Refer `redis.md` for exact key list and usage.
#     5. If `profile_picture` is provided:
#         - Delete existing one using `picture_id` (if exists).
#         - Save the new picture and update the URL in DB.
#     
#     Refer to API: `/student/me/update-profile` for request/response structure.
#     Apply the above logic for the `clerk` role.



# @router.put("/me/update-profile")
# async def update_profile(
#     credentials: HTTPAuthorizationCredentials = Depends(security),
#     user_data: dict = Depends(is_logged_in)
# ):





# This Route is used to fetch all students for dept same as clerk dept 
# Clerk Dept is stored in the jwt token :- user_data["department"]
# Req body :- Program , Semester , Academic year will be passed by the clerk to the function 
# Call the function :- fetch_class(user_data, request) {services/teachers/}
# student:{program}:{department}:{semester} ( This redis key , might have all data of students)
# If not save to this 
# Just return array of :- 

# {
#       "student_id": "1FE27D332D414E72854A3F40C7F9CCBF",
#       "name": "Deepak Kumar Yadav",
#       "roll_number": 69,
#       "email": "deepak.yadav24@spit.ac.in",
#       "phone": "9821293538",
#       "department": "BTECH",
#       "program": "MCA",
#       "semester": 6,
#       "batch_year": 2024,
#       "profile_picture": "https://ik.imagekit.io/v4ughtdwn/profile_image/266cd98ac05c40c8b6959464d7aaea8a_zd8KCMK5A.jpg"
# }


# @router.put("/students")
# async def update_profile(
#    request: ClassSearchRequest,
#     credentials: HTTPAuthorizationCredentials = Depends(security),
#     user_data: dict = Depends(is_logged_in)
# ):





