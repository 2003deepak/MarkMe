from fastapi import Request
from fastapi.responses import JSONResponse
from bson import ObjectId
from datetime import timezone

from app.models.allModel import StudentListingView
from app.schemas.attendance import Attendance
from app.schemas.session import Session
from app.schemas.exception_session import ExceptionSession
from app.schemas.subject import Subject
from app.schemas.teacher import Teacher
from app.schemas.student import Student


async def get_attendance_by_id(request: Request, attendance_id: str):

    # ------------------------------------------------------------------
    # STEP 1 — VALIDATION
    # ------------------------------------------------------------------
    if not ObjectId.is_valid(attendance_id):
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Invalid attendance ID"}
        )

    # ------------------------------------------------------------------
    # STEP 2 — FETCH ATTENDANCE
    # ------------------------------------------------------------------
    attendance = await Attendance.get(ObjectId(attendance_id), fetch_links=True)

    if not attendance:
        return JSONResponse(
            status_code=404,
            content={"success": False, "message": "Attendance not found"}
        )

    # ------------------------------------------------------------------
    # STEP 3 — RESOLVE EFFECTIVE SESSION
    # ------------------------------------------------------------------
    session: Session | None = None
    exception: ExceptionSession | None = None

    if attendance.session:
        session = attendance.session

    elif attendance.exception_session:
        exception = await ExceptionSession.get(
            attendance.exception_session.id,
            fetch_links=True
        )
        if exception:
            session = exception.session

    if not session:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "Unable to resolve session for this attendance"
            }
        )

    # ------------------------------------------------------------------
    # STEP 4 — FETCH SUBJECT & TEACHER
    # ------------------------------------------------------------------
    subject = await Subject.get(session.subject.id)
    teacher = await Teacher.get(session.teacher.id)

    if not subject or not teacher:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "Subject or Teacher data missing"
            }
        )

    # ------------------------------------------------------------------
    # STEP 5 — HANDLE EXCEPTION SESSION TIMING
    # ------------------------------------------------------------------
    exception_data = None
    actual_start_time = session.start_time
    actual_end_time = session.end_time

    if exception:
        exception_data = {
            "action": exception.action,
            "date": exception.date.date().isoformat(),
            "start_time": exception.start_time,
            "end_time": exception.end_time,
        }
        actual_start_time = exception.start_time
        actual_end_time = exception.end_time

    # ------------------------------------------------------------------
    # STEP 6 — FETCH STUDENTS (ORDER IS CRITICAL)
    # ------------------------------------------------------------------
    students = await Student.find(
        Student.program == session.program,
        Student.department == session.department,
        Student.semester == int(session.semester),
        Student.batch_year == int(session.academic_year),
    ).project(StudentListingView).sort("roll_number").to_list()

    bitmask = attendance.students or ""

    present_students = []
    absent_students = []

    for idx, student in enumerate(students):
        is_present = idx < len(bitmask) and bitmask[idx] == "1"
        
        student_data = { 
                        "id": str(student.student_id), 
                        "name": student.first_name + " " + student.last_name, 
                        "roll_no": student.roll_number, 
                        "profile_picture" : student.profile_picture
                    }

        if is_present:
            present_students.append(student_data)
        else:
            absent_students.append(student_data)

    # ------------------------------------------------------------------
    # STEP 7 — BUILD FINAL RESPONSE
    # ------------------------------------------------------------------
    return {
        "success": True,
        "message": "Attendance detail fetched successfully",

        "attendance": {
            "attendance_id": str(attendance.id),
            "marked_date": attendance.date.date().isoformat(),
            "marked_time": attendance.created_at.astimezone(
                timezone.utc
            ).strftime("%H:%M:%S"),
            "is_exception_session": attendance.exception_session is not None,
        },

        "session": {
            "session_id": str(session.id),
            "subject": subject.subject_name,
            "component": subject.component,
            "program": session.program,
            "department": session.department,
            "semester": session.semester,
            "academic_year": session.academic_year,
            "scheduled_time": {
                "start": session.start_time,
                "end": session.end_time,
            },
            "actual_time": {
                "start": actual_start_time,
                "end": actual_end_time,
            },
            "exception": exception_data,
        },

        "teacher": {
            "id": str(teacher.id),
            "name": f"{teacher.first_name} {teacher.last_name}",
            "email": teacher.email,
        },

        "students": {
            "total": len(students),
            "present_count": len(present_students),
            "absent_count": len(absent_students),
            "present": present_students,
            "absent": absent_students,
        }
    }
