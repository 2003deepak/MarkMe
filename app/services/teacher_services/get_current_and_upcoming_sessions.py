from bson import DBRef
from fastapi import status, Request
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.schemas.teacher import Teacher
from app.schemas.session import Session
from app.schemas.attendance import Attendance
from app.schemas.exception_session import ExceptionSession


async def get_current_and_upcoming_sessions(request: Request):

    print("\n===================== FETCH SESSIONS API START =====================")

    # -------------------------------------------------------------------
    # STEP 1 — Validate Teacher
    # -------------------------------------------------------------------
    user_role = request.state.user.get("role")
    user_email = request.state.user.get("email")

    if user_role != "teacher":
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Only teachers can access this endpoint"}
        )

    teacher = await Teacher.find_one(Teacher.email == user_email)
    if not teacher:
        return JSONResponse(
            status_code=404,
            content={"success": False, "message": "Teacher not found"}
        )

    # -------------------------------------------------------------------
    # STEP 2 — Date Context
    # -------------------------------------------------------------------
    current_time = datetime.now(tz=ZoneInfo("Asia/Kolkata"))
    today_date = current_time.date()
    weekday_name = current_time.strftime("%A")
    # weekday_name = "Friday"

    day_start = datetime.combine(today_date, datetime.min.time()).replace(tzinfo=ZoneInfo("Asia/Kolkata"))
    day_end   = datetime.combine(today_date, datetime.max.time()).replace(tzinfo=ZoneInfo("Asia/Kolkata"))

    # -------------------------------------------------------------------
    # STEP 3 — Base Sessions (LINK SAFE FILTER)
    # -------------------------------------------------------------------
    session_list = await Session.find(
        Session.day == weekday_name,
        Session.teacher.id == teacher.id,
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
            add_exceptions.append(ex)
        else:
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
    # STEP 7 — Fetch Attendance (with both session & exception_session)
    # -------------------------------------------------------------------
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
        # NEW LOGIC — Map to attendance even if only exception_session matches
        # -------------------------------------------------------------------
        attendance = attendance_by_id.get(session_id)

        date_str = today_date.strftime("%Y-%m-%d")

        start_time = datetime.strptime(
            f"{date_str} {start_time_str}", "%Y-%m-%d %H:%M"
        ).replace(tzinfo=ZoneInfo("Asia/Kolkata"))

        end_time = datetime.strptime(
            f"{date_str} {end_time_str}", "%Y-%m-%d %H:%M"
        ).replace(tzinfo=ZoneInfo("Asia/Kolkata"))

        # -------------------------------------------------------------------
        # NEW FEATURE: Attendance ID if start_time < 15 minutes away
        # -------------------------------------------------------------------
        attendance_id = None

        if attendance:
            attendance_id = str(attendance.id)
        else:
            diff = (start_time - current_time).total_seconds()
            if 0 <= diff <= 900:  # within 15 mins to start
                attendance_id = "GENERATE_NOW"  # OR None → your choice

        session_data = {
            "session_id": session_id,
            "attendance_id": attendance_id,
            "date": date_str,
            "start_time": start_time_str,
            "end_time": end_time_str,
            "subject_name": subject.subject_name,
            "subject_code": subject.subject_code,
            "component": subject.component,
            "program": program,
            "department": department,
            "semester": semester,
            "academic_year": academic_year,
            "teacher_name": f"{teacher_obj.first_name} {teacher_obj.last_name}",
        }

        # Put into categories
        if start_time <= current_time <= end_time:
            current.append(session_data)
        elif start_time > current_time:
            upcoming.append(session_data)
        else:
            past.append(session_data)

    # -------------------------------------------------------------------
    # STEP 9 — Sort
    # -------------------------------------------------------------------
    for arr in (upcoming, current, past):
        arr.sort(key=lambda x: datetime.strptime(
            f"{x['date']} {x['start_time']}", "%Y-%m-%d %H:%M"
        ))

    # -------------------------------------------------------------------
    # STEP 10 — Return Response
    # -------------------------------------------------------------------
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "Sessions fetched successfully",
            "data": {
                "upcoming": upcoming,
                "current": current,
                "past": past
            }
        }
    )
