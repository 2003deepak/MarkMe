from fastapi import (
    APIRouter,
    Request,
    Path,
    Form,
    UploadFile,
    File,
    HTTPException
)
from typing import Optional

from fastapi.responses import JSONResponse

# --- Service Imports
from app.services.clerk_services.get_clerk_profile import get_clerk_profile
from app.services.clerk_services.create_teacher import create_teacher
from app.services.clerk_services.create_subject import create_subject
from app.services.clerk_services.update_clerk import update_clerk
from app.services.clerk_services.update_teacher import update_teacher_data
from app.services.teacher_services.get_all_teachers import get_all_teachers
from app.services.teacher_services.get_teacher_detail import get_teacher_by_id
from app.services.teacher_services.fetch_class_list import fetch_class
from app.services.clerk_services.add_timetable import add_timetable
from app.services.clerk_services.get_subject_detail import get_subject_detail, get_subject_by_id

# --- Pydantic Imports
from app.models.allModel import (
    TeacherUpdateRequest,
    UpdateClerkRequest,
    CreateSubjectRequest,
    TeacherRegisterRequest,
    TimeTableRequest
)

router = APIRouter()


# ------------------- Subject Routes -------------------

@router.post("/subject")
async def create_subject_route(
    request_model: CreateSubjectRequest,
    request: Request
):
    return await create_subject(request, request_model)


@router.get("/subject")
async def get_subject_route(request: Request):
    return await get_subject_detail(request)


@router.get("/subject/{subject_id}")
async def get_subject_by_id_route(
    request: Request,
    subject_id: str = Path(..., description="Subject ID to fetch details for")
):
    return await get_subject_by_id(request, subject_id)


# ------------------- Teacher Routes -------------------

@router.post("/teacher")
async def create_teacher_route(
    request_model: TeacherRegisterRequest,
    request: Request
):
    return await create_teacher(request, request_model)

@router.patch("/teacher")
async def update_teacher(
    request_model: TeacherUpdateRequest,
    request: Request
):
    return await update_teacher_data(request, request_model)


@router.get("/teacher")
async def get_all_teachers_route(request: Request):
    return await get_all_teachers(request)


@router.get("/teacher/{teacher_id}")
async def get_teacher_route(
    request: Request,
    teacher_id: str = Path(..., description="Teacher ID to fetch details for")
):
    return await get_teacher_by_id(request, teacher_id)


# ------------------- Clerk Routes -------------------


@router.get("/me")
async def get_clerk_profile_route(request: Request):
    return await get_clerk_profile(request)

    
# ------------------- Student Routes -------------------


@router.put("/me")
async def update_clerk_route(
    request: Request,
    first_name: Optional[str] = Form(None),
    middle_name: Optional[str] = Form(None),
    last_name: Optional[str] = Form(None),
    phone: Optional[str] = Form(None), 
    profile_picture: Optional[UploadFile] = File(None),
):
    # Debug logging
    print(f"Received inputs: first_name={first_name}, middle_name={middle_name}, last_name={last_name}, "
          f"phone={phone}, profile_picture={profile_picture}")

    # Utility: clean empty strings
    def clean(value: Optional[str]) -> Optional[str]:
        return None if value is None or str(value).strip() == "" else value

    # Clean inputs
    first_name = clean(first_name)
    middle_name = clean(middle_name)
    last_name = clean(last_name)
   

    # Parse phone
    phone_int: Optional[int] = None
    if phone:
        try:
            phone_int = int(phone.strip())
        except ValueError:
            return JSONResponse(
                status_code=422,
                content={
                    "success": False, 
                    "message": "Invalid integer value for phone"
                }
            )

    update_request_data = UpdateClerkRequest(
        first_name=first_name,
        middle_name=middle_name,
        last_name=last_name,
        phone=phone_int,
    )

    return await update_clerk(
        request=request,
        request_data=update_request_data,
        profile_picture=profile_picture
    )
# ------------------- Student Routes -------------------

@router.get("/students")
async def get_students_route(
    batch_year: int,
    program: str,
    semester: int,
    request: Request
):
    print(f"Received request for /students with params: batch_year={batch_year}, program={program}, semester={semester}")
    return await fetch_class(request, batch_year, program, semester)



