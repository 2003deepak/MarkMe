from datetime import datetime, timedelta
from bson import ObjectId
from fastapi import Request
from fastapi.responses import JSONResponse
from zoneinfo import ZoneInfo

from app.schemas.session import Session
from app.schemas.exception_session import ExceptionSession
from app.schemas.student_attendance_summary import StudentAttendanceSummary


async def get_tomorrow_bunk_safety(request: Request):

    print("\n===================== TOMORROW BUNK SAFETY START =====================")

    # STEP 1 — Validate Student
    user = request.state.user
    if user.get("role") != "student":
        print("❌ Not a student. Access denied.")
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Only students can access this endpoint"}
        )

    student_id = str(user.get("id"))
    prog = user.get("program")
    sem = str(user.get("semester"))
    ac_year = str(user.get("batch_year"))
    dept = user.get("department")

    print(f"👤 Student ID: {student_id}")
    print(f"🎓 Program: {prog} | Sem: {sem} | Year: {ac_year} | Dept: {dept}")

    # STEP 2 — Compute Tomorrow's Date
    now = datetime.now(tz=ZoneInfo("Asia/Kolkata"))
    tomorrow_date = now.date() + timedelta(days=1)
    tomorrow_weekday = (now + timedelta(days=1)).strftime("%A")

    print(f"\n📅 Tomorrow Date: {tomorrow_date} ({tomorrow_weekday})")

    day_start = datetime.combine(tomorrow_date, datetime.min.time()).replace(tzinfo=ZoneInfo("Asia/Kolkata"))
    day_end = datetime.combine(tomorrow_date, datetime.max.time()).replace(tzinfo=ZoneInfo("Asia/Kolkata"))


    # STEP 3 — Fetch Base Sessions
    base_sessions = await Session.find(
        Session.day == tomorrow_weekday,
        Session.program == prog,
        Session.semester == sem,
        Session.academic_year == ac_year,
        Session.department == dept,
        fetch_links=True
    ).to_list()

    print(f"\n📘 Base Timetable Sessions for Tomorrow: {len(base_sessions)}")
    for s in base_sessions:
        print(f"   ➤ NORMAL SESSION: {s.subject.id} ({s.subject.component}) {s.start_time} - {s.end_time}")


    # STEP 4 — Exception Sessions
    exceptions = await ExceptionSession.find(
        {"date": {"$gte": day_start, "$lte": day_end}},
        fetch_links=True
    ).to_list()

    print(f"\n⚠️ Exception Sessions Found: {len(exceptions)}")

    cancel_resched_map = {}
    add_list = []

    for ex in exceptions:
        subj = ex.session.subject
        sid = str(subj.id)

        if ex.action == "Add":
            print(f"   ➕ ADD Exception for Subject: {sid} ({subj.component})")
            add_list.append(ex)

        elif ex.action == "Cancel":
            print(f"   ❌ CANCEL Exception for Subject: {sid}")
            cancel_resched_map[str(ex.session.id)] = ex

        elif ex.action == "Rescheduled":
            print(f"   🔄 RESCHEDULE Exception for Subject: {sid}")
            cancel_resched_map[str(ex.session.id)] = ex

    
    # STEP 5 — Apply Exceptions
    final_sessions = []

    for ses in base_sessions:
        sid = str(ses.id)

        if sid in cancel_resched_map:
            ex = cancel_resched_map[sid]

            if ex.action == "Cancel":
                print(f"   ❌ Removing CANCELLED SESSION {ses.subject.id}")
                continue

            if ex.action == "Rescheduled":
                print(f"   🔄 Updating SESSION {ses.subject.id} Timing → {ex.start_time} to {ex.end_time}")
                ses.start_time = ex.start_time
                ses.end_time = ex.end_time

        final_sessions.append(ses)

    # Add virtual ADD sessions
    for ex in add_list:
        src = ex.session
        print(f"   ➕ ADDING VIRTUAL SESSION {src.subject.id} ({src.subject.component})")

        final_sessions.append({
            "_is_added": True,
            "id": str(ex.id),
            "start_time": ex.start_time,
            "end_time": ex.end_time,
            "subject": src.subject,
            "teacher": src.teacher,
            "program": src.program,
            "department": src.department,
            "semester": src.semester,
            "academic_year": src.academic_year,
            "day": tomorrow_weekday
        })

    print(f"\n📘 FINAL Combined Sessions for Tomorrow: {len(final_sessions)}")
    for s in final_sessions:
        if isinstance(s, dict):
            print(f"   ➤ FINAL ADD: {s['subject'].id} ({s['subject'].component}) {s['start_time']} - {s['end_time']}")
        else:
            print(f"   ➤ FINAL NORMAL: {s.subject.id} ({s.subject.component}) {s.start_time} - {s.end_time}")


    # STEP 6 — Fetch Student Attendance Summary Per Subject ID
    attendance_stats_docs = await StudentAttendanceSummary.find(
        StudentAttendanceSummary.student.id == ObjectId(student_id),
        fetch_links=True
    ).to_list()

    print(f"\n📊 Attendance Summary Docs: {len(attendance_stats_docs)}")

    subject_map = {}
    total_attended = 0
    total_conducted = 0

    for doc in attendance_stats_docs:
        subj = doc.subject
        sid = str(subj.id)

        attended = doc.attended
        conducted = doc.total_classes
        percentage = doc.percentage

        print(f"   ➤ Summary for {sid}: {attended}/{conducted} = {percentage:.2f}%")

        subject_map[sid] = {
            "subject_name": subj.subject_name,
            "subject_code": subj.subject_code,
            "component": subj.component,     # ✅ FIX ADDED
            "attended": attended,
            "conducted": conducted,
            "attendance_now": percentage
        }

        total_attended += attended
        total_conducted += conducted


    # STEP 7 — Identify Tomorrow Subjects By ID
    tomorrow_subjects = set()

    for ses in final_sessions:
        subject = ses["subject"] if isinstance(ses, dict) else ses.subject
        sid = str(subject.id)
        tomorrow_subjects.add(sid)

    print(f"\n📚 Subjects Tomorrow: {tomorrow_subjects}")

    # Ensure missing subjects have default structure
    for sid in tomorrow_subjects:
        if sid not in subject_map:
            print(f"   ⚠️ No attendance summary for {sid}, initializing defaults")
            subject_map[sid] = {
                "subject_name": None,
                "subject_code": None,
                "component": None,
                "attended": 0,
                "conducted": 0,
                "attendance_now": 0.0
            }

    # STEP 8 — Simulate IF BUNK impact
    print("\n📉 Simulating IF BUNK Impact...")
    for sid in tomorrow_subjects:
        sub = subject_map[sid]
        att = sub["attended"]
        cond = sub["conducted"]

        after_bunk_pct = (att / (cond + 1) * 100) if (cond + 1) else 0
        sub["attendance_if_bunk"] = after_bunk_pct
        sub["safe"] = after_bunk_pct >= 75

        print(f"   ➤ {sid}: NOW={sub['attendance_now']:.2f}% | IF BUNK={after_bunk_pct:.2f}% | SAFE={sub['safe']}")

    # STEP 9 — Aggregate Simulation
    aggregate_now = (total_attended / total_conducted * 100) if total_conducted else 0

    total_if_bunk = total_conducted + len(final_sessions)
    aggregate_if_bunk = (total_attended / total_if_bunk * 100) if total_if_bunk else 0

    print(f"\n📊 Aggregate NOW: {aggregate_now:.2f}%")
    print(f"📉 Aggregate IF BUNK: {aggregate_if_bunk:.2f}%")

    
    # STEP 10 — Decision
    safe_to_bunk = all(subject_map[sid]["safe"] for sid in tomorrow_subjects) and (aggregate_if_bunk >= 75)

    print(f"\n🟩 SAFE TO BUNK? {safe_to_bunk}")


    # STEP 11 — Build HTTP Response
    response_subjects = []
    for sid in sorted(tomorrow_subjects):
        sub = subject_map[sid]
        response_subjects.append({
            "subject_id": sid,
            "subject_name": sub["subject_name"],
            "subject_code": sub["subject_code"],
            "component": sub["component"],   # ✅ NOW SHOWING PROPERLY
            "attended": sub["attended"],
            "conducted": sub["conducted"],
            "attendance_now": round(sub["attendance_now"], 2),
            "attendance_if_bunk": round(sub["attendance_if_bunk"], 2),
            "safe": sub["safe"]
        })

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "Tomorrow bunk safety calculated",
            "data": {
                "date": str(tomorrow_date),
                "safe_to_bunk": safe_to_bunk,
                "subjects": response_subjects,
                "aggregate": {
                    "current": round(aggregate_now, 2),
                    "if_bunk": round(aggregate_if_bunk, 2),
                    "tomorrow_session_count": len(final_sessions)
                }
            }
        }
    )


async def get_week_plan(request: Request):

    print("\n\n===================== WEEKLY BUNK SAFETY START =====================")


    # STEP 1 — VALIDATE STUDENT
    
    user = request.state.user
    if user.get("role") != "student":
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Only students can access this endpoint"}
        )

    student_id = str(user.get("id"))
    prog = user.get("program")
    sem = str(user.get("semester"))
    ac_year = str(user.get("batch_year"))
    dept = user.get("department")

    tz = ZoneInfo("Asia/Kolkata")
    today = datetime.now(tz=tz).date()

    
    # STEP 2 — LOAD ATTENDANCE SUMMARY (OPTIONAL)
    
    attendance_docs = await StudentAttendanceSummary.find(
        StudentAttendanceSummary.student.id == ObjectId(student_id),
        fetch_links=True
    ).to_list()

    subject_map = {}
    total_attended = 0
    total_conducted = 0

    for doc in attendance_docs:
        subj = doc.subject
        sid = str(subj.id)

        subject_map[sid] = {
            "subject_name": subj.subject_name,
            "subject_code": subj.subject_code,
            "component": subj.component,
            "attended": doc.attended,
            "conducted": doc.total_classes,
            "attendance_now": doc.percentage,
        }

        total_attended += doc.attended
        total_conducted += doc.total_classes

    print(f"📊 Attendance summary loaded: {len(subject_map)} subjects")

    
    # STEP 3 — LOAD WEEKLY BASE SESSIONS
    
    weekly_sessions = await Session.find(
        Session.program == prog,
        Session.semester == sem,
        Session.academic_year == ac_year,
        Session.department == dept,
        fetch_links=True
    ).to_list()

    sessions_by_day = {}
    for ses in weekly_sessions:
        sessions_by_day.setdefault(ses.day, []).append(ses)

    print(f"📘 Weekly base sessions loaded: {len(weekly_sessions)}")

    
    # STEP 4 — DETERMINE DAYS LEFT
    
    weekday_index = today.weekday()  # Monday=0
    days_left = 0 if weekday_index == 6 else 6 - weekday_index

    week_start = today + timedelta(days=1)
    week_end = today + timedelta(days=days_left)

    
    # STEP 5 — LOAD EXCEPTION SESSIONS
    
    exceptions = await ExceptionSession.find(
        {
            "date": {
                "$gte": datetime.combine(week_start, datetime.min.time(), tzinfo=tz),
                "$lte": datetime.combine(week_end, datetime.max.time(), tzinfo=tz)
            }
        },
        fetch_links=True
    ).to_list()

    exceptions_by_date = {}
    for ex in exceptions:
        exceptions_by_date.setdefault(ex.date.date(), []).append(ex)

    
    # STEP 6 — BUILD WEEK PLAN
    
    weekly_plan = []

    for i in range(1, days_left + 1):
        date = today + timedelta(days=i)
        weekday = date.strftime("%A")

        base_sessions = sessions_by_day.get(weekday, [])
        todays_ex = exceptions_by_date.get(date, [])

        cancel_or_resched = {}
        add_list = []

        for ex in todays_ex:
            sid = str(ex.session.id)
            if ex.action == "Add":
                add_list.append(ex)
            else:
                cancel_or_resched[sid] = ex

        final_sessions = []

        for ses in base_sessions:
            sid = str(ses.id)

            if sid in cancel_or_resched:
                ex = cancel_or_resched[sid]

                if ex.action == "Cancel":
                    continue

                if ex.action == "Rescheduled":
                    ses.start_time = ex.start_time
                    ses.end_time = ex.end_time

            final_sessions.append(ses)

        for ex in add_list:
            final_sessions.append({
                "_is_added": True,
                "subject": ex.session.subject,
                "start_time": ex.start_time,
                "end_time": ex.end_time
            })

        
        # STEP 7 — COLLECT SUBJECT METADATA FROM SESSIONS (CRITICAL FIX)
        
        todays_subjects = {}

        for ses in final_sessions:
            subject = ses["subject"] if isinstance(ses, dict) else ses.subject
            sid = str(subject.id)

            if sid not in todays_subjects:
                todays_subjects[sid] = {
                    "subject_name": subject.subject_name,
                    "subject_code": subject.subject_code,
                    "component": subject.component
                }

        # Merge attendance data (or defaults)
        for sid, meta in todays_subjects.items():
            if sid not in subject_map:
                subject_map[sid] = {
                    **meta,
                    "attended": 0,
                    "conducted": 0,
                    "attendance_now": 0.0
                }

        
        # STEP 8 — CALCULATE SAFETY
        
        day_results = []
        safe_today = True

        for sid in todays_subjects:
            sub = subject_map[sid]
            att = sub["attended"]
            cond = sub["conducted"]

            after_pct = (att / (cond + 1) * 100) if cond + 1 else 0
            safe = after_pct >= 75

            if not safe:
                safe_today = False

            day_results.append({
                "subject_id": sid,
                "subject_name": sub["subject_name"],
                "subject_code": sub["subject_code"],
                "component": sub["component"],
                "attendance_now": sub["attendance_now"],
                "attendance_if_bunk": round(after_pct, 2),
                "safe": safe
            })

        agg_now = (total_attended / total_conducted * 100) if total_conducted else 0
        total_if = total_conducted + len(final_sessions)
        agg_if = (total_attended / total_if * 100) if total_if else 0

        if agg_if < 75:
            safe_today = False

        weekly_plan.append({
            "date": str(date),
            "weekday": weekday,
            "safe_to_bunk": safe_today,
            "subjects": day_results,
            "aggregate": {
                "current": round(agg_now, 2),
                "if_bunk": round(agg_if, 2),
                "session_count": len(final_sessions)
            }
        })

    summary = [
        {
            "date": d["date"],
            "weekday": d["weekday"],
            "recommended": "BUNK" if d["safe_to_bunk"] else "ATTEND"
        }
        for d in weekly_plan
    ]

    print("\n===================== WEEK PLAN COMPLETE =====================")

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "Weekly bunk safety calculated",
            "data": {
                "week_plan": weekly_plan,
                "summary": summary
            }
        }
    )
