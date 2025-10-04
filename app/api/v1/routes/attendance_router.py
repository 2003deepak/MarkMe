from fastapi import APIRouter, HTTPException, Depends, Query

from app.services.common_services.get_student_attendance_summary import get_student_attendance_summary


router = APIRouter()


# 👨‍🎓 Student APIs


@router.get("/student/{student_id}/summary")
async def get_student_summary(
    student_id: str,

):
   
    return await get_student_attendance_summary(student_id)


@router.get("/student/{student_id}/subject/{subject_id}")
async def get_student_subject_attendance(student_id: str, subject_id: str):

    return {"message": f"Attendance for student {student_id} in subject {subject_id}"}


@router.get("/student/{student_id}/subject/{subject_id}/history")
async def get_student_subject_history(student_id: str, subject_id: str):

    return {"message": f"History for student {student_id} in subject {subject_id}"}


# 🏛️ Admin APIs

@router.get("/admin/departments")
async def get_department_wise_attendance():
    """
    Get department-wise average attendance percentages.
    Example: FYMCA = 82%, SYMCA = 85%.
    """
    return {"message": "Department-wise attendance"}


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
