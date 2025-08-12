from fastapi import HTTPException
from app.schemas.attendance import Attendance
from app.core.redis import redis_client
from datetime import datetime
from bson import ObjectId

async def mark_student_attendance(attendance_id: str, attendance_student: str, user_data: dict):
    # Step 1: Verify user role is teacher
    if user_data.get("role") != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can mark attendance")
    
    # Step 2: Fetch attendance record with nested session and teacher details
    try:
        attendance_record = await Attendance.get(attendance_id, fetch_links=True)
        if not attendance_record:
            raise HTTPException(status_code=404, detail="Attendance record not found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid attendance ID: {str(e)}")
    
    # Step 3: Validate time frame and teacher email
    current_time = datetime.now().time()
    current_date = datetime.now().date()
    
    # Extract session details (assuming session is a linked document in Beanie)
    session = attendance_record.session
    if not session:
        raise HTTPException(status_code=400, detail="Session details not found")
    
    start_time = session.start_time
    end_time = session.end_time
    session_day = session.day
    
    # Validate teacher email (assuming teacher is a linked document in session)
    if not session.teacher:
        raise HTTPException(status_code=400, detail="Teacher details not found in session")
    if session.teacher.email != user_data.get("email"):
        raise HTTPException(status_code=403, detail="Teacher not authorized for this session")
    
    # Validate day
    if session_day.lower() != current_date.strftime("%A").lower():
        raise HTTPException(status_code=400, detail="Attendance cannot be marked on a different day")
    
    # # Validate time frame
    try:
        start = datetime.strptime(start_time, "%H:%M").time()
        end = datetime.strptime(end_time, "%H:%M").time()
        if not (start <= current_time <= end):
            raise HTTPException(status_code=400, detail="Attendance can only be marked within session time")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid time format in session")
    

    
    # Ensure attendance_student is a string/bitmask
    if not isinstance(attendance_student, str) or not set(attendance_student) <= {"0", "1"}:
        raise HTTPException(status_code=400, detail="Attendance must be a binary string of 0 and 1")

    # # Check length
    # if len(session.students) != len(attendance_student):
    #     raise HTTPException(status_code=400, detail="Invalid attendance string — it does not match class strength")


    try:
        attendance_record.students = attendance_student
        update_result = await attendance_record.save()
        if not update_result:
            raise HTTPException(status_code=400, detail="No changes made to attendance")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update attendance: {str(e)}")
    
    # Step 5: Return success message
    return {"message": "Attendance marked successfully", "attendance_id": attendance_id}