from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from app.schemas.attendance import Attendance
from app.core.redis import redis_client
from datetime import datetime
from bson import ObjectId

async def mark_student_attendance(request: Request, attendance_id: str, attendance_student: str):
    # Step 1: Verify user role is teacher
    user_role = request.state.user.get("role")
    user_email = request.state.user.get("email")
    
    if user_role != "teacher":
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "message": "Only teachers can mark attendance"
            }
        )
    
    # Step 2: Fetch attendance record with nested session and teacher details
    try:
        attendance_record = await Attendance.get(attendance_id, fetch_links=True)
        if not attendance_record:
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "message": "Attendance record not found"
                }
            )
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": f"Invalid attendance ID: {str(e)}"
            }
        )
    
    # Step 3: Validate time frame and teacher email
    current_time = datetime.now().time()
    current_date = datetime.now().date()
    
    # Extract session details (assuming session is a linked document in Beanie)
    session = attendance_record.session
    if not session:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "Session details not found"
            }
        )
    
    start_time = session.start_time
    end_time = session.end_time
    session_day = session.day
    
    # Validate teacher email (assuming teacher is a linked document in session)
    if not session.teacher:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "Teacher details not found in session"
            }
        )
    if session.teacher.email != user_email:
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "message": "Teacher not authorized for this session"
            }
        )
    
    # Validate day
    if session_day.lower() != current_date.strftime("%A").lower():
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "Attendance cannot be marked on a different day"
            }
        )
    
    # Validate time frame
    try:
        start = datetime.strptime(start_time, "%H:%M").time()
        end = datetime.strptime(end_time, "%H:%M").time()
        if not (start <= current_time <= end):
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "message": "Attendance can only be marked within session time"
                }
            )
    except ValueError:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "Invalid time format in session"
            }
        )
    
    # Ensure attendance_student is a string/bitmask
    if not isinstance(attendance_student, str) or not set(attendance_student) <= {"0", "1"}:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "Attendance must be a binary string of 0 and 1"
            }
        )

    # # Check length (commented out as in original code)
    # if len(session.students) != len(attendance_student):
    #     raise HTTPException(status_code=400, detail="Invalid attendance string — it does not match class strength")

    try:
        attendance_record.students = attendance_student
        update_result = await attendance_record.save()
        if not update_result:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "message": "No changes made to attendance"
                }
            )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"Failed to update attendance: {str(e)}"
            }
        )
    
    # Step 5: Return success message
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "Attendance marked successfully",
            "data": {
                "attendance_id": attendance_id
            }
        }
    )