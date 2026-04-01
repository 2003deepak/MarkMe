import asyncio
import random
from datetime import datetime, timedelta

from app.core.database import init_db
from app.schemas.session import Session
from app.schemas.exception_session import ExceptionSession
from app.schemas.attendance import Attendance
from app.schemas.student import Student
from app.schemas.swap_approval import SwapApproval

#probabilities
CANCEL_PROB = 0.1
RESCHEDULE_PROB = 0.12
ADD_SESSION_PROB = 0.2

START_DATE = datetime(2026, 1, 1)
END_DATE = datetime(2026, 4, 1)

WEEKDAYS = [
    "Monday", "Tuesday", "Wednesday",
    "Thursday", "Friday", "Saturday", "Sunday"
]

#helpers
def time_diff_minutes(start, end):
    sh, sm = map(int, start.split(":"))
    eh, em = map(int, end.split(":"))
    return (eh * 60 + em) - (sh * 60 + sm)

def add_minutes(time_str, minutes):
    h, m = map(int, time_str.split(":"))
    total = h * 60 + m + minutes
    return f"{(total // 60) % 24:02d}:{total % 60:02d}"

def random_evening_start():
    return f"{random.randint(16, 18):02d}:00"

def random_float(a, b):
    return random.uniform(a, b)

def generate_bitstring(n, rate):
    return "".join("1" if random.random() < rate else "0" for _ in range(n))

#fetch all exceptions for date
async def get_exceptions_by_date(date):
    return await ExceptionSession.find(
        ExceptionSession.date == date,
        fetch_links=True
    ).to_list()

#fetch exception for session
async def get_exception(session_id, date):
    return await ExceptionSession.find_one(
        ExceptionSession.session.id == session_id,
        ExceptionSession.date == date
    )

async def run():
    await init_db()

    students = await Student.find(
        Student.program == "MSC",
        Student.department == "IT",
        Student.batch_year == 2026,
        Student.semester == 2
    ).to_list()

    sessions = await Session.find(
        Session.program == "MSC",
        Session.department == "IT",
        Session.semester == "2",
        Session.academic_year == "2026",
        fetch_links=True
    ).to_list()

    if not students or not sessions:
        print("Base data missing")
        return

    #group sessions
    sessions_by_day = {}
    for s in sessions:
        sessions_by_day.setdefault(s.day, []).append(s)

    date_cursor = START_DATE

    while date_cursor <= END_DATE:

        weekday = WEEKDAYS[date_cursor.weekday()]
        todays_sessions = sessions_by_day.get(weekday, [])

        # ---------------- HANDLE EXCEPTION-ONLY (CRITICAL) ----------------
        all_exceptions = await get_exceptions_by_date(date_cursor)

        handled_session_ids = set()

        for ex in all_exceptions:

            if ex.action == "Cancel":
                continue

            #skip if will be handled in session loop
            if ex.session and ex.session.day == weekday:
                continue

            attendance = Attendance(
                session=None,
                exception_session=ex,
                date=date_cursor,
                start_time=ex.start_time,
                end_time=ex.end_time,
                students="",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            await attendance.insert()

            attendance.students = generate_bitstring(
                len(students),
                random_float(0.6, 0.9)
            )
            await attendance.save()

        # ---------------- NORMAL SESSION LOOP ----------------
        for sess in todays_sessions:

            #strict validation
            if sess.day != weekday:
                continue

            if not sess.teacher:
                continue

            roll = random.random()
            target_date = date_cursor

            # CANCEL
            if roll < CANCEL_PROB:

                ex = ExceptionSession(
                    session=sess,
                    subject=sess.subject,
                    teacher=sess.teacher,
                    action="Cancel",
                    reason="Auto generated cancel",
                    date=target_date,
                    created_by=sess.teacher,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                await ex.insert()
                continue

            # RESCHEDULE
            elif roll < CANCEL_PROB + RESCHEDULE_PROB:

                duration = time_diff_minutes(sess.start_time, sess.end_time)
                new_start = random_evening_start()
                new_end = add_minutes(new_start, duration)

                ex = ExceptionSession(
                    session=sess,
                    subject=sess.subject,
                    teacher=sess.teacher,
                    action="Reschedule",
                    reason="Auto generated reschedule",
                    date=target_date,
                    start_time=new_start,
                    end_time=new_end,
                    created_by=sess.teacher,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                await ex.insert()

            # ADD
            elif roll < CANCEL_PROB + RESCHEDULE_PROB + ADD_SESSION_PROB:

                duration = time_diff_minutes(sess.start_time, sess.end_time)
                new_start = add_minutes(sess.end_time, random.choice([60, 120]))
                new_end = add_minutes(new_start, duration)

                ex = ExceptionSession(
                    session=sess,
                    subject=sess.subject,
                    teacher=sess.teacher,
                    action="Add",
                    reason="Auto generated additional session",
                    date=target_date,
                    start_time=new_start,
                    end_time=new_end,
                    created_by=sess.teacher,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                await ex.insert()

            # ---------------- ATTENDANCE ----------------
            existing_exception = await get_exception(sess.id, target_date)

            #skip cancel
            if existing_exception and existing_exception.action == "Cancel":
                continue

            if existing_exception:
                attendance = Attendance(
                    session=None,
                    exception_session=existing_exception,
                    date=target_date,
                    start_time=existing_exception.start_time,
                    end_time=existing_exception.end_time,
                    students="",
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
            else:
                attendance = Attendance(
                    session=sess,
                    exception_session=None,
                    date=target_date,
                    start_time=sess.start_time,
                    end_time=sess.end_time,
                    students="",
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )

            await attendance.insert()

            attendance.students = generate_bitstring(
                len(students),
                random_float(0.6, 0.9)
            )
            await attendance.save()

        date_cursor += timedelta(days=1)

    print("Seeding completed successfully")


if __name__ == "__main__":
    asyncio.run(run())