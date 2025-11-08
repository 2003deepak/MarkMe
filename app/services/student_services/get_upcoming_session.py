from datetime import datetime, time
from typing import Any, Dict
from zoneinfo import ZoneInfo
from fastapi import Request
from fastapi.responses import JSONResponse

from app.schemas.session import Session
from app.schemas.student import Student
from app.schemas.exception_session import ExceptionSession


async def get_todays_upcoming_sessions_for_student(request: Request) -> Dict[str, Any]:
    
    # 1. Check if user is a student and fetch student data
    user_role = request.state.user.get("role")
    user_email = request.state.user.get("email")
    
    if user_role != "student":
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Only students can access this endpoint"}
        )

    student = await Student.find_one(Student.email == user_email)
    if not student:
        return JSONResponse(
            status_code=404,
            content={"success": False, "message": "Student not found"}
        )

    # 2. Get student details (convert to same format as session)
    student_program = student.program
    student_semester = str(student.semester)  # Convert to string to match session
    student_academic_year = str(student.batch_year)  # Convert to string to match session
    student_department = student.department

    print(f"Student: {student_program}, {student_semester}, {student_academic_year}, {student_department}")

    # 3. Get current date and time in IST
    current_time = datetime.now(tz=ZoneInfo("Asia/Kolkata"))
    today = current_time.date()
    current_weekday = current_time.strftime("%A")
    current_time_str = current_time.strftime("%H:%M")

    print(f"Today: {today}, Weekday: {current_weekday}, Current Time: {current_time_str}")

    # 4. Query TODAY'S SESSIONS matching student's criteria
    try:
        session_list = await Session.find({
            "program": student_program,
            "semester": student_semester,
            "academic_year": student_academic_year,
            "department": student_department,
            "day": current_weekday  # Only today's sessions
        }).to_list()

        print(f"Found {len(session_list)} sessions for today")

        # Fetch linked data for sessions
        for session in session_list:
            await session.fetch_link("subject")
            await session.fetch_link("teacher")
            print(f"Session: {session.start_time} - {session.end_time}")

    except Exception as e:
        print(f"Error fetching sessions: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "Failed to fetch session records"}
        )

    # 5. Get all exception sessions for today
    session_ids = [session.id for session in session_list]
    
    # Convert today date to datetime for query
    today_start = datetime.combine(today, time.min).replace(tzinfo=ZoneInfo("Asia/Kolkata"))
    today_end = datetime.combine(today, time.max).replace(tzinfo=ZoneInfo("Asia/Kolkata"))
    
    exception_sessions = await ExceptionSession.find({
        "session": {"$in": session_ids},
        "date": {"$gte": today_start, "$lte": today_end}
    }).to_list()

    print(f"Found {len(exception_sessions)} exception sessions")

    # Create dictionaries for different exception types
    cancelled_sessions = {}
    rescheduled_sessions = {}

    for exception in exception_sessions:
        if not exception.session:
            continue
            
        session_id = str(exception.session.id)
        
        if exception.action == "Cancel":
            cancelled_sessions[session_id] = exception
        elif exception.action == "Rescheduled":
            rescheduled_sessions[session_id] = exception

    # 6. Process regular sessions and handle exceptions
    upcoming_sessions = []
    
    for session in session_list:
        try:
            session_id = str(session.id)
            
            # Skip if session is cancelled
            if session_id in cancelled_sessions:
                print(f"Session {session_id} is cancelled, skipping")
                continue

            # Check if session is rescheduled
            if session_id in rescheduled_sessions:
                exception = rescheduled_sessions[session_id]
                start_time_str = exception.start_time
                end_time_str = exception.end_time
                status = "rescheduled"
                notes = f"Rescheduled to {start_time_str} - {end_time_str}"
                print(f"Session {session_id} is rescheduled to {start_time_str}")
            else:
                start_time_str = session.start_time
                end_time_str = session.end_time
                status = "scheduled"
                notes = None

            # Create timezone-aware datetime objects for session timing
            start_time = datetime.strptime(f"{today} {start_time_str}", "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo("Asia/Kolkata"))
            
            # Check if session is upcoming (start time is after current time)
            is_upcoming = start_time > current_time

            print(f"Session {start_time_str}: upcoming={is_upcoming}, current={current_time_str}")

            if is_upcoming:
                # Calculate time until start
                time_diff = start_time - current_time
                minutes_until_start = int(time_diff.total_seconds() // 60)
                hours = minutes_until_start // 60
                minutes = minutes_until_start % 60
                
                time_display = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
                
                session_data = {
                    "session_id": session_id,
                    "start_time": start_time_str,
                    "end_time": end_time_str,
                    "subject_name": session.subject.subject_name if session.subject else None,
                    "component": session.subject.component if session.subject else None,
                    "teacher_name": f"{session.teacher.first_name} {session.teacher.last_name}" if session.teacher else None,
                    "status": status,
                    "time_until_start_minutes": minutes_until_start,
                    "time_until_start_display": time_display
                }
                upcoming_sessions.append(session_data)
                print(f"Added upcoming session: {start_time_str} - {end_time_str}")

        except Exception as e:
            print(f"Error processing session {session.id}: {str(e)}")
            continue

    # 7. Sort by start time (earliest first)
    upcoming_sessions.sort(key=lambda x: datetime.strptime(x['start_time'], "%H:%M"))

    # 8. Construct final response
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "Today's upcoming sessions fetched successfully",
            "data": {
                "date": str(today),
                "day": current_weekday,
                "current_time": current_time_str,
                "upcoming_sessions": upcoming_sessions
            }
        }
    )