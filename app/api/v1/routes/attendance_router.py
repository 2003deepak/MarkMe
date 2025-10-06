from fastapi import APIRouter, HTTPException, Depends, Path, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.middleware.is_logged_in import is_logged_in
from typing import Any, Dict, Optional
from app.services.common_services.get_attendance_summary_department import get_attendance_summary_department
from app.services.common_services.get_student_attendance_summary import get_student_attendance_summary
from app.services.common_services.get_student_subject_wise import get_student_subject_wise


router = APIRouter()
security = HTTPBearer()  # Define security scheme


# 👨‍🎓 Student APIs


@router.get("/student/summary/{student_id}")
async def get_student_summary(
    student_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in),
):
    return await get_student_attendance_summary(student_id, user_data)


@router.get("/student/{student_id}/subject/{subject_id}")
async def get_student_subject_attendance(
    student_id: str = Path(..., description="The ID of the student"),
    subject_id: str = Path(..., description="The ID of the subject"),
    month: Optional[int] = Query(None, description="Month (1-12)", ge=1, le=12),
    year: Optional[int] = Query(None, description="Year (e.g., 2025)"),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in),
):
    return await get_student_subject_wise(student_id, subject_id, month, year, user_data)


# 🏛️ Admin APIs

@router.get("/admin/departments/{department_name}")
async def get_department_wise_attendance(
    department_name: str,
    program: Optional[str] = Query(None, description="Program name (e.g., B.Tech, MCA)"),
    month: int = Query(..., ge=1, le=12, description="Month number (1-12)"),
    year: int = Query(..., description="Year (e.g., 2025)")
) -> Dict[str, Any]:
    """
    Get department/program-wise average attendance percentages by subject for a given month & year.
    """
    return await get_attendance_summary_department(
        department_name=department_name,
        program=program,
        month=month,
        year=year
    )


@router.get("/admin/top-teachers")
async def get_top_teachers():
    """
    Get top performing teachers ranked by highest average student attendance
    across their subjects.
    """
    return {"message": "Top performing teachers list"}


@router.get("/admin/students/critical-risk")
async def get_critical_risk_students():
    """
    Get list of students across the college with attendance below 40%.
    Helps identify critical risk students.
    """
    return {"message": "Critical risk students list"}


# 👨‍💼 Clerk APIs

@router.get("/clerk/subject/{subject_id}/average")
async def get_subject_average(subject_id: str):
    """
    Get average attendance percentage for a specific subject
    across all enrolled students.
    """
    return {"message": f"Average attendance for subject {subject_id}"}


@router.get("/clerk/subject/{subject_id}/defaulters")
async def get_subject_defaulters(subject_id: str):
    """
    Get list of students in a subject with attendance below 75%.
    """
    return {"message": f"Defaulter list for subject {subject_id}"}


@router.get("/clerk/heatmap/{department_id}")
async def get_department_heatmap(department_id: str):
    """
    Get heatmap data for a department.
    Shows days with lowest average attendance.
    """
    return {"message": f"Attendance heatmap for department {department_id}"}
