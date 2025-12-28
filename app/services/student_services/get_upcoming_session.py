from datetime import datetime
from typing import Any, Dict
from zoneinfo import ZoneInfo
from fastapi import Request
from fastapi.responses import JSONResponse

from app.schemas.session import Session
from app.schemas.exception_session import ExceptionSession
from app.schemas.attendance import Attendance

IST = ZoneInfo("Asia/Kolkata")


async def get_todays_upcoming_sessions_for_student(
    request: Request
) -> Dict[str, Any]:

    # STEP 1 — Auth
    user = request.state.user
    if user.get("role") != "student":
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "message": "Only students can access this endpoint"
            }
        )

    # STEP 2 — Date context
    now = datetime.now(tz=IST)
    today = now.date()
    weekday = now.strftime("%A")

    day_start = datetime.combine(today, datetime.min.time(), tzinfo=IST)
    day_end = datetime.combine(today, datetime.max.time(), tzinfo=IST)

    # STEP 3 — Student scope
    program = user.get("program")
    semester = str(user.get("semester"))
    academic_year = str(user.get("batch_year"))
    department = user.get("department")

    # STEP 4 — Base sessions
    base_sessions = await Session.find(
        Session.day == weekday,
        Session.program == program,
        Session.semester == semester,
        Session.academic_year == academic_year,
        Session.department == department,
        fetch_links=True
    ).to_list()

    base_session_map = {str(s.id): s for s in base_sessions}

    # STEP 5 — Exceptions (today only)
    exceptions = await ExceptionSession.find(
        ExceptionSession.date >= day_start,
        ExceptionSession.date <= day_end,
        fetch_links=True
    ).to_list()

    cancel_set = set()
    reschedule_map = {}
    target_exceptions = []
    add_exceptions = []

    # STEP 6 — Process exceptions
    for ex in exceptions:

        # swap must be approved
        if ex.swap_id and ex.swap_id.status != "APPROVED":
            continue

        # ADD
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

        # CANCEL
        if ex.action == "Cancel":
            cancel_set.add(sid)

        # RESCHEDULE
        elif ex.action == "Reschedule":
            reschedule_map[sid] = ex

            if ex.swap_role == "TARGET":
                target_exceptions.append(ex)

    # STEP 7 — Apply base sessions
    final_sessions = []
    added_ids = set()

    for sid, session in base_session_map.items():

        if sid in cancel_set:
            continue

        if sid in reschedule_map:
            ex = reschedule_map[sid]
            session.start_time = ex.start_time
            session.end_time = ex.end_time

        final_sessions.append(session)
        added_ids.add(sid)

    # STEP 8 — Inject TARGET swap sessions
    for ex in target_exceptions:
        sid = str(ex.session.id)
        if sid not in added_ids:
            injected = ex.session
            injected.start_time = ex.start_time
            injected.end_time = ex.end_time
            final_sessions.append(injected)
            added_ids.add(sid)

    # STEP 9 — ADD virtual sessions
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

    # STEP 10 — Attendance
    attendance_list = await Attendance.find(
        Attendance.date >= day_start,
        Attendance.date <= day_end,
        fetch_links=True
    ).to_list()

    attendance_map = {}
    for a in attendance_list:
        if a.session:
            attendance_map[str(a.session.id)] = a
        elif a.exception_session:
            attendance_map[str(a.exception_session.id)] = a

    # STEP 11 — Categorize sessions
    upcoming, current, past = [], [], []

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

        start_dt = datetime.strptime(
            f"{today} {start_str}", "%Y-%m-%d %H:%M"
        ).replace(tzinfo=IST)

        end_dt = datetime.strptime(
            f"{today} {end_str}", "%Y-%m-%d %H:%M"
        ).replace(tzinfo=IST)

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

        if start_dt <= now <= end_dt:
            current.append(payload)
        elif start_dt > now:
            mins = int((start_dt - now).total_seconds() // 60)
            payload["time_until_start_display"] = (
                f"{mins//60}hr {mins%60}m"
                if mins >= 60 else f"{mins}m"
            )
            upcoming.append(payload)
        else:
            past.append(payload)

    # STEP 12 — Sort
    for arr in (upcoming, current, past):
        arr.sort(
            key=lambda x: datetime.strptime(
                f"{x['date']} {x['start_time']}",
                "%Y-%m-%d %H:%M"
            )
        )

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
