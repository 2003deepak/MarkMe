from fastapi import APIRouter, Request, Path , Query
from typing import Literal, Optional
from datetime import datetime

from sympy import limit
from app.services.admin_services.manage_clerk import create_clerk, edit_clerk, get_clerk, get_clerk_by_id
from app.services.admin_services.get_live_classes import get_live_classes
from app.services.admin_services.teacher_leaderboard import get_teacher_leaderboard
from app.services.admin_services.teacher_defaulters import teacher_defaulters
from app.services.admin_services.get_extremes import get_extremes
from app.services.admin_services.get_reports import download_class_report
from app.services.admin_services.list_metadata import list_metadata
from app.services.admin_services.program_services import create_program, get_program_by_id, update_program, list_all_programs
from app.services.admin_services.department_services import create_department, get_department_by_id, update_department, list_all_departments
from app.models.allModel import (
    CreateClerkRequest, 
    TeacherLeaderboardRequest, 
    CreateProgramRequest,
    UpdateAcademicScopesRequest, 
    UpdateProgramRequest, 
    CreateDepartmentRequest, 
    UpdateDepartmentRequest
)

router = APIRouter()


@router.get("/metadata/all")
async def list_metadata_route(request: Request):
    return await list_metadata(request)

# Program Routes
@router.post("/program")
async def create_program_route(request: Request, request_model: CreateProgramRequest):
    return await create_program(request, request_model)

@router.get("/programs/all")
async def list_programs_route(request: Request):
    return await list_all_programs(request)

@router.get("/program/{id}")
async def get_program_route(request: Request, id: str = Path(...)):
    return await get_program_by_id(request, id)

@router.patch("/program/{id}")
async def update_program_route(request: Request, id: str = Path(...), request_model: UpdateProgramRequest = None):
    return await update_program(request, id, request_model)



# Department Routes
@router.post("/department")
async def create_department_route(request: Request, request_model: CreateDepartmentRequest):
    return await create_department(request, request_model)

@router.get("/departments/all")
async def list_departments_route(request: Request):
    return await list_all_departments(request)

@router.get("/department/{id}")
async def get_department_route(request: Request, id: str = Path(...)):
    return await get_department_by_id(request, id)

@router.patch("/department/{id}")
async def update_department_route(request: Request, id: str = Path(...), request_model: UpdateDepartmentRequest = None):
    return await update_department(request, id, request_model)


@router.get("/live-classes")
async def get_live_classes_route(request: Request):
    return await get_live_classes(request)

@router.get("/teacher-leaderboard")
async def get_teacher_leaderboard_route(
    request: Request,
    department: Optional[str] = None,
    program: Optional[str] = None,
    period: Optional[str] = "monthly",   #weekly | monthly | custom
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
):
    return await get_teacher_leaderboard(
        request=request,
        department=department,
        program=program,
        period=period,
        start_date=start_date,
        end_date=end_date
    )

@router.get("/extremes")
async def get_extremes_route(
    request: Request,
    department: Optional[str] = None,
    program: Optional[str] = None,
):
    return await get_extremes(
        request=request,
        department=department,
        program=program
    )


# Update clerk by ID    
@router.patch("/clerk/{clerk_id}")
async def update_clerk_route(
    request: Request,
    clerk_id: str,
    body: UpdateAcademicScopesRequest
):
    return await edit_clerk(request, clerk_id, body)
    
# Create Clerk
@router.post("/clerk")
async def create_clerk_route(
    request_model: CreateClerkRequest,
    request: Request
):
    return await create_clerk(request, request_model)


# Get clerks
@router.get("/clerk")
async def get_clerk_route(
    request: Request = None,
    department: Optional[str] = None,
    program: Optional[str] = None,
    search: Optional[str] = None,
    page: Optional[int] = 1,
    limit: Optional[int] = 10
    
):
    return await get_clerk(request, department,program, search, page, limit)




# Get clerk by email
@router.get("/clerk/{clerk_id}")
async def get_clerk_by_id_route(
    request: Request ,
    clerk_id: str = Path(..., description="Clerk ID"),
):
    return await get_clerk_by_id(request,clerk_id)





@router.get("/teacher/defaulters")
async def get_teacher_defaulters(
    request: Request,
    page: int = 1,
    limit: int = 10,
):
    return await teacher_defaulters(request, page, limit)



@router.get("/download-class-report/{department}/{program}/{semester}/{batch_year}/{file_type}")
async def download_class_report_api(
    request: Request,
    department: str,
    program: str,
    semester: int,
    batch_year: int,
    file_type : Literal["excel", "pdf"] = str
):
    return await download_class_report(
        request=request,
        department=department,
        program=program,
        semester=semester,
        batch_year=batch_year,
        file_type=file_type
    )
