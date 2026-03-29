from fastapi import APIRouter, HTTPException, Depends, Path, Query, Request

from typing import Any, Dict, Optional

from fastapi.responses import JSONResponse
from app.services.common_services.attendance_history import clerk_attendance_history, student_attendance_history, teacher_attendance_history
from app.services.common_services.detailed_attendance import get_attendance_by_id
from app.services.common_services.get_heatmap import get_heatmap
from app.services.common_services.get_attendance_summary_department import get_attendance_summary_department
from app.services.common_services.get_student_attendance_summary import get_student_attendance_summary
from app.services.common_services.get_student_subject_wise import get_student_subject_wise
from app.utils.parse_data import parse_comma_separated_list


router = APIRouter()


# 👨‍🎓 Student APIs


@router.get("/student/summary")
async def get_student_summary(request: Request, student_id: Optional[str] = None):
    return await get_student_attendance_summary(request, student_id)



@router.get("/student/{student_id}/subject/{subject_id}")
async def get_student_subject_attendance(
    request : Request,
    student_id: str = Path(..., description="The ID of the student"),
    subject_id: str = Path(..., description="The ID of the subject"),
    month: Optional[int] = Query(None, description="Month (1-12)", ge=1, le=12),
    year: Optional[int] = Query(None, description="Year (e.g., 2025)")
):

    return await get_student_subject_wise(request , student_id,subject_id,month,year)


# 🏛️ Admin APIs

@router.get("/admin/departments/{department_name}")
async def get_department_wise_attendance(
    department_name: str,
    month: int = Query(..., ge=1, le=12, description="Month number (1-12)"),
    year: int = Query(..., description="Year (e.g., 2025)")
) -> Dict[str, Any]:
    """
    Get department/program-wise average attendance percentages by subject for a given month & year.
    """
    return await get_attendance_summary_department(
        department_name=department_name,
        month=month,
        year=year
    )


# 👨‍💼 Clerk APIs

@router.get("/heatmap")
async def get_department_heatmap(
    department: Optional[str] = Query(None, description="Department name"),
    program: Optional[str] = Query(None, description="Program name"),
    semester: Optional[int] = Query(None, description="Semester number"),
    month: Optional[int] = Query(None, description="Month number (1-12)"),
    year: Optional[int] = Query(None, description="Year (e.g., 2025)"),
):
    return await get_heatmap(department, program, semester, month, year)



@router.get("/history")
async def get_department_heatmap(
    request: Request,
    department: Optional[str] = Query(None, description="Department name (comma-separated)"),
    program: Optional[str] = Query(None, description="Program name (comma-separated)"),
    batch_year: Optional[str] = Query(None, description="Batch year (comma-separated)"),
    semester: Optional[str] = Query(None, description="Semester numbers (comma-separated)"),
    subject: Optional[str] = Query(None, description="Subject IDs (comma-separated)"),
    month: Optional[int] = Query(None, description="Month number (1-12)"),
    year: Optional[int] = Query(None, description="Year (e.g., 2025)"),
):
    user = request.state.user
    role = user["role"]
    
    # Parse comma-separated strings into lists
    subject_list = parse_comma_separated_list(subject)
    program_list = parse_comma_separated_list(program)
    department_list = parse_comma_separated_list(department)
    
    # Parse batch_year and semester as integers
    batch_year_list = None
    semester_list = None
    
    if batch_year:
        try:
            batch_year_list = [int(year.strip()) for year in batch_year.split(",") if year.strip()]
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "Invalid batch_year format"}
            )
    
    if semester:
        try:
            semester_list = [int(sem.strip()) for sem in semester.split(",") if sem.strip()]
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "Invalid semester format"}
            )

    if role == "student":
        return await student_attendance_history(request, month, year, subject_list)

    if role == "teacher":
        return await teacher_attendance_history(request, month, year, subject_list)

    if role == "clerk":
        return await clerk_attendance_history(
            request, month, year, subject_list, department_list,program_list, batch_year_list,semester_list
        )
        
@router.get("/{attendance_id}")
async def deatiled_attendance(
    request: Request,
    attendance_id: str = Path(..., description="Teacher ID to fetch details for")
    
):
    
        return await get_attendance_by_id(
            request,
            attendance_id
        )