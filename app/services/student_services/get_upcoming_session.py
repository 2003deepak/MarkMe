from datetime import datetime
from typing import Any, Dict
from zoneinfo import ZoneInfo
from fastapi import Request
from fastapi.responses import JSONResponse

from app.schemas.session import Session
from app.schemas.exception_session import ExceptionSession
from app.schemas.attendance import Attendance
from app.utils.parse_data import validate_student_academic

IST = ZoneInfo("Asia/Kolkata")


async def get_todays_upcoming_sessions_for_student(
    request: Request
) -> Dict[str, Any]:

    #auth
    user = request.state.user
    if user.get("role") != "student":
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Only students allowed"}
        )

    #time context
    now = datetime.now(tz=IST)
    today = now.date()
    weekday = now.strftime("%A")

    #student scope
    program = user.get("program")
    semester = str(user.get("semester"))
    academic_year = str(user.get("batch_year"))
    department = user.get("department")

    missing = validate_student_academic(user)
    if missing:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "Student academic details incomplete",
                "missing_fields": missing
            }
        )

    #base sessions
    base_sessions = await Session.find(
        Session.day == weekday,
        Session.program == program,
        Session.semester == semester,
        Session.academic_year == academic_year,
        Session.department == department,
        Session.is_active == True,
        fetch_links=True
    ).to_list()

    base_map = {str(s.id): s for s in base_sessions}

    #today exceptions only
    exceptions = await ExceptionSession.find(
        ExceptionSession.date == today,
        fetch_links=True
    ).to_list()

    cancel_set = set()
    reschedule_map = {}
    target_exceptions = []
    add_exceptions = []

    #process exceptions
    for ex in exceptions:

        #ignore non-approved swaps
        if ex.swap_id and ex.swap_id.status != "APPROVED":
            continue

        #ADD
        if ex.action == "Add":
            if (
                ex.program == program and
                ex.semester == semester and
                ex.academic_year == academic_year and
                ex.department == department
            ):
                add_exceptions.append(ex)
            continue

        if not ex.session:
            continue

        sid = str(ex.session.id)

        if ex.action == "Cancel":
            cancel_set.add(sid)

        elif ex.action == "Reschedule":
            reschedule_map[sid] = ex

            if ex.swap_role == "TARGET":
                target_exceptions.append(ex)

    #final session list
    final_sessions = []
    added_ids = set()

    #normal + reschedule
    for sid, session in base_map.items():

        if sid in cancel_set:
            continue

        if sid in reschedule_map:
            ex = reschedule_map[sid]
            session.start_time = ex.start_time
            session.end_time = ex.end_time

        final_sessions.append(session)
        added_ids.add(sid)

    #inject swap target sessions
    for ex in target_exceptions:
        sid = str(ex.session.id)
        if sid not in added_ids:
            injected = ex.session
            injected.start_time = ex.start_time
            injected.end_time = ex.end_time
            final_sessions.append(injected)
            added_ids.add(sid)

    #add virtual sessions (ADD)
    for ex in add_exceptions:
        final_sessions.append({
            "_is_added": True,
            "id": str(ex.id),
            "start_time": ex.start_time,
            "end_time": ex.end_time,
            "subject": ex.subject,
            "teacher": ex.created_by,
            "program": ex.program,
            "department": ex.department,
            "semester": ex.semester,
            "academic_year": ex.academic_year,
        })

    #attendance (today only)
    attendance_list = await Attendance.find(
        Attendance.date == today,
        fetch_links=True
    ).to_list()

    attendance_map = {}
    for a in attendance_list:
        if a.session:
            attendance_map[str(a.session.id)] = a
        elif a.exception_session:
            attendance_map[str(a.exception_session.id)] = a

    #filter upcoming
    upcoming = []

    for s in final_sessions:

        if isinstance(s, dict):
            session_id = s["id"]
            start_str = s["start_time"]
            end_str = s["end_time"]
            subject = s["subject"]
            teacher = s["teacher"]
            program = s["program"]
            department = s["department"]
            semester = s["semester"]
            academic_year = s["academic_year"]
        else:
            session_id = str(s.id)
            start_str = s.start_time
            end_str = s.end_time
            subject = s.subject
            teacher = s.teacher
            program = s.program
            department = s.department
            semester = s.semester
            academic_year = s.academic_year

        #convert time
        start_dt = datetime.strptime(
            f"{today} {start_str}", "%Y-%m-%d %H:%M"
        ).replace(tzinfo=IST)

        #only upcoming
        if start_dt <= now:
            continue

        attendance = attendance_map.get(session_id)

        payload = {
            "session_id": session_id,
            "attendance_id": str(attendance.id) if attendance else None,
            "date": today.strftime("%Y-%m-%d"),
            "start_time": start_str,
            "end_time": end_str,
            "subject_name": subject.subject_name if subject else None,
            "subject_code": subject.subject_code if subject else None,
            "component": subject.component if subject else None,
            "program": program,
            "department": department,
            "semester": semester,
            "academic_year": academic_year,
            "teacher_name": (
                f"{teacher.first_name} {teacher.last_name}"
                if teacher else None
            )
        }

        upcoming.append(payload)

    #sort
    upcoming.sort(
        key=lambda x: datetime.strptime(
            f"{x['date']} {x['start_time']}",
            "%Y-%m-%d %H:%M"
        )
    )

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "Upcoming sessions fetched successfully",
            "data": {
                "upcoming": upcoming
            }
        }
    )