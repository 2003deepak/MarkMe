from fastapi import APIRouter, Depends, Body, Path, Form, UploadFile, File, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.services.clerk_services.create_teacher import create_teacher
from app.services.clerk_services.create_subject import create_subject
from app.services.clerk_services.update_clerk import update_clerk
from app.middleware.is_logged_in import is_logged_in
from app.services.teacher_services.get_all_teachers import get_all_teachers
from app.services.teacher_services.get_teacher_detail import get_teacher_by_id
from app.services.teacher_services.fetch_class_list import fetch_class
from app.services.clerk_services.add_timetable import add_timetable
from app.services.clerk_services.get_subject_detail import get_subject_detail,get_subject_by_id
from app.models.allModel import ClassSearchRequest, UpdateClerkRequest
from typing import Optional, List


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


@router.put("/me/update-profile")
async def update_clerk_route(
    first_name: Optional[str] = Form(None),
    middle_name: Optional[str] = Form(None),
    last_name: Optional[str] = Form(None),
    phone: Optional[int] = Form(None),
    department: Optional[str] = Form(None),
    program: Optional[str] = Form(None),
    profile_picture: Optional[UploadFile] = File(None),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in),
):
    # Debug logging to inspect incoming values
    print(f"Received inputs: first_name={first_name}, middle_name={middle_name}, last_name={last_name}, phone={phone}, department={department}, program={program}, profile_picture={profile_picture}")

    # Convert empty strings to None
    def clean(value: Optional[str]) -> Optional[str]:
        return None if value is None or str(value).strip() == "" else value

    # Clean string inputs
    first_name = clean(first_name)
    middle_name = clean(middle_name)
    last_name = clean(last_name)
    department = clean(department)
    program = clean(program)

    # Parse phone as integer
    phone_int: Optional[int] = None
    if phone:
        try:
            phone_int = int(phone.strip())
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail={"status": "fail", "message": "Invalid integer value for phone"}
            )

    update_request_data = UpdateClerkRequest(
        first_name=first_name,
        middle_name=middle_name,
        last_name=last_name,
        phone=phone_int,
        department=department,
        program=program,
    )

    return await update_clerk(
        request_data=update_request_data,
        user_data=user_data,
        profile_picture=profile_picture
    )


@router.post("/students")
async def get_students(
    request: ClassSearchRequest,  # Query parameters
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in),
):
    print(f"Received request for /students with data: {request.dict()}")

    # Validate user role
    if user_data["role"] != "clerk":
        print(f"Unauthorized access attempt by role: {user_data['role']}")
        raise HTTPException(
            status_code=403,
            detail={"status": "fail", "message": "Only clerks can access student profiles"}
        )

    # Get department from user_data
    department = user_data.get("department")
    if not department:
        print("No department found in user_data")
        raise HTTPException(
            status_code=400,
            detail={"status": "fail", "message": "Clerk department not specified"}
        )

    return await fetch_class(
        user_data,
        request
    )





