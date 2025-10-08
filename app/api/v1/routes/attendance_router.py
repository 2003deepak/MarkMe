from fastapi import APIRouter, HTTPException, Depends, Path, Query, Request

from typing import Any, Dict, Optional

from fastapi.responses import JSONResponse
from app.services.common_services.get_heatmap import get_heatmap
from app.services.common_services.subject_wise_attendance import subject_wise_attendance
from app.services.common_services.get_critical_students import get_critical_students
from app.services.common_services.get_teacher_avg_attendance import get_teacher_avg_attendance
from app.services.common_services.get_attendance_summary_department import get_attendance_summary_department
from app.services.common_services.get_student_attendance_summary import get_student_attendance_summary
from app.services.common_services.get_student_subject_wise import get_student_subject_wise


router = APIRouter()


# 👨‍🎓 Student APIs


@router.get("/student/summary/{student_id}")
async def get_student_summary(
    
    request: Request,
    student_id: str,

):
   
    return await get_student_attendance_summary(request , student_id)


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


@router.get("/departments/{department_name}/teachers/attendance-summary")
async def get_teacher_summary(
    request: Request,
    department_name: str,
    program: Optional[str] = None,
    semester: Optional[int] = None,
):
    return await get_teacher_avg_attendance(request, department_name, program, semester)


@router.get("/students/critical-risk")
async def get_critical_risk_students(
    request: Request,
    department: Optional[str] = Query(None, description="Department name, e.g., MCA"),
    program: Optional[str] = Query(None, description="Program name, e.g., MCA"),
    semester: Optional[int] = Query(None, description="Semester number, e.g., 3"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Number of items per page"),
):
    return await get_critical_students(
        request=request,
        department=department,
        program=program,
        semester=semester,
        page=page,
        limit=limit
    )

# 👨‍💼 Clerk APIs

@router.get("/subject/{subject_id}")
async def get_subject_wise_attendance(request: Request, subject_id: str):
    return await subject_wise_attendance(request, subject_id)


@router.get("/heatmap")
async def get_department_heatmap(
    department: Optional[str] = Query(None, description="Department name"),
    program: Optional[str] = Query(None, description="Program name"),
    batch_year: Optional[int] = Query(None, description="Batch year"),
    semester: Optional[int] = Query(None, description="Semester number"),
    month: Optional[int] = Query(None, description="Month number (1-12)"),
    year: Optional[int] = Query(None, description="Year (e.g., 2025)"),
):
    return await get_heatmap(department, program, batch_year, semester, month, year)
