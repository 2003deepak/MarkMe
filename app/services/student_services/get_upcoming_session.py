from datetime import datetime
from typing import Any, Dict
from zoneinfo import ZoneInfo
from fastapi import Request
from fastapi.responses import JSONResponse

from app.schemas.session import Session
from app.schemas.session import Session
from app.schemas.exception_session import ExceptionSession
from app.schemas.attendance import Attendance


async def get_todays_upcoming_sessions_for_student(request: Request) -> Dict[str, Any]:
    
    print("\n===================== FETCH STUDENT SESSIONS START =====================")

    # -------------------------------------------------------------------
    # STEP 1 — Validate Student
    # -------------------------------------------------------------------
    user_data = request.state.user
    user_role = user_data.get("role")
    
    if user_role != "student":
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Only students can access this endpoint"}
        )

    # -------------------------------------------------------------------
    # STEP 2 — Date Context
    # -------------------------------------------------------------------
    current_time = datetime.now(tz=ZoneInfo("Asia/Kolkata"))
    today_date = current_time.date()
    weekday_name = current_time.strftime("%A")

    day_start = datetime.combine(today_date, datetime.min.time()).replace(tzinfo=ZoneInfo("Asia/Kolkata"))
    day_end   = datetime.combine(today_date, datetime.max.time()).replace(tzinfo=ZoneInfo("Asia/Kolkata"))


    # STEP 3 — Base Sessions
    student_program = user_data.get("program")
    student_semester = str(user_data.get("semester"))
    student_academic_year = str(user_data.get("batch_year"))
    student_department = user_data.get("department")

    session_list = await Session.find(
        Session.day == weekday_name,
        Session.program == student_program,
        Session.semester == student_semester,
        Session.academic_year == student_academic_year,
        Session.department == student_department,
        fetch_links=True
    ).to_list()

    # -------------------------------------------------------------------
    # STEP 4 — Exception Sessions
    # -------------------------------------------------------------------
    exception_list = await ExceptionSession.find(
        {"date": {"$gte": day_start, "$lte": day_end}},
        fetch_links=True
    ).to_list()

    exception_map = {}
    add_exceptions = []

    for ex in exception_list:
        if ex.action == "Add":
            # For Add exceptions, check if the session targets this student
            if ex.session:
                base = ex.session
                if (base.program == student_program and
                    base.semester == student_semester and
                    base.academic_year == student_academic_year and
                    base.department == student_department):
                    add_exceptions.append(ex)
        else:
            if ex.session:
                exception_map[str(ex.session.id)] = ex

    # -------------------------------------------------------------------
    # STEP 5 — Apply CANCEL / RESCHEDULE
    # -------------------------------------------------------------------
    final_sessions = []

    for session in session_list:
        sid = str(session.id)

        if sid in exception_map:
            ex = exception_map[sid]

            if ex.action == "Cancel":
                continue

            if ex.action == "Rescheduled":
                session.start_time = ex.start_time
                session.end_time = ex.end_time

        final_sessions.append(session)

    # -------------------------------------------------------------------
    # STEP 6 — ADD (Virtual Sessions)
    # -------------------------------------------------------------------
    for ex in add_exceptions:
        base = ex.session

        new_session = {
            "_is_added": True,
            "id": str(ex.id),                        # EXCEPTION SESSION ID
            "start_time": ex.start_time,
            "end_time": ex.end_time,
            "subject": base.subject,
            "teacher": base.teacher,
            "program": base.program,
            "department": base.department,
            "semester": base.semester,
            "academic_year": base.academic_year,
            "day": weekday_name
        }

        final_sessions.append(new_session)

    # -------------------------------------------------------------------
    # STEP 7 — Fetch Attendance
    # -------------------------------------------------------------------
    # We fetch attendance for this student only
    attendance_list = await Attendance.find(
        {"date": {"$gte": day_start, "$lte": day_end}},
        fetch_links=True
    ).to_list()
    
    
    attendance_by_id = {}
    for a in attendance_list:
        if a.session:
            attendance_by_id[str(a.session.id)] = a
        elif a.exception_session:
            attendance_by_id[str(a.exception_session.id)] = a

    # -------------------------------------------------------------------
    # STEP 8 — Build response objects
    # -------------------------------------------------------------------
    upcoming, current, past = [], [], []

    for session in final_sessions:

        if isinstance(session, dict):
            session_id      = session["id"]
            start_time_str  = session["start_time"]
            end_time_str    = session["end_time"]
            subject         = session["subject"]
            teacher_obj     = session["teacher"]
            program         = session["program"]
            department      = session["department"]
            semester        = session["semester"]
            academic_year   = session["academic_year"]
        else:
            session_id      = str(session.id)
            start_time_str  = session.start_time
            end_time_str    = session.end_time
            subject         = session.subject
            teacher_obj     = session.teacher
            program         = session.program
            department      = session.department
            semester        = session.semester
            academic_year   = session.academic_year

        # -------------------------------------------------------------------
        # Attendance Logic
        # -------------------------------------------------------------------
        attendance = attendance_by_id.get(session_id)

        date_str = today_date.strftime("%Y-%m-%d")

        start_time = datetime.strptime(
            f"{date_str} {start_time_str}", "%Y-%m-%d %H:%M"
        ).replace(tzinfo=ZoneInfo("Asia/Kolkata"))

        end_time = datetime.strptime(
            f"{date_str} {end_time_str}", "%Y-%m-%d %H:%M"
        ).replace(tzinfo=ZoneInfo("Asia/Kolkata"))

        attendance_id = str(attendance.id) if attendance else None

        session_data = {
            "session_id": session_id,
            "attendance_id": attendance_id,
            "date": date_str,
            "start_time": start_time_str,
            "end_time": end_time_str,
            "subject_name": subject.subject_name if subject else None,
            "subject_code": subject.subject_code if subject else None,
            "component": subject.component if subject else None,
            "program": program,
            "department": department,
            "semester": semester,
            "academic_year": academic_year,
            "teacher_name": f"{teacher_obj.first_name} {teacher_obj.last_name}" if teacher_obj else None,
        }

        # Put into categories
        if start_time <= current_time <= end_time:
            current.append(session_data)
        elif start_time > current_time:
            # Calculate time remaining
            diff = start_time - current_time
            total_seconds = int(diff.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            
            if hours > 0 and minutes > 0:
                display = f"{hours}hr {minutes}m"
            elif hours > 0:
                display = f"{hours}hr"
            else:
                display = f"{minutes}m"
                
            session_data["time_until_start_display"] = display
            upcoming.append(session_data)
        else:
            past.append(session_data)


    # STEP 9 — Sort
    for arr in (upcoming, current, past):
        arr.sort(key=lambda x: datetime.strptime(
            f"{x['date']} {x['start_time']}", "%Y-%m-%d %H:%M"
        ))

    # STEP 10 — Return Response
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "Student sessions fetched successfully",
            "data": {
                "upcoming": upcoming,
                "current": current,
                "past": past
            }
        }
    )