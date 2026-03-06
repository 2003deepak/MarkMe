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
SWAP_PROB = 0.3
SWAP_REJECT_PROB = 0.35

START_DATE = datetime(2025, 6, 11)
END_DATE = datetime(2025, 12, 10)

WEEKDAYS = [
    "Sunday", "Monday", "Tuesday",
    "Wednesday", "Thursday", "Friday", "Saturday"
]

#helpers

def time_diff_minutes(start: str, end: str) -> int:
    sh, sm = map(int, start.split(":"))
    eh, em = map(int, end.split(":"))
    return (eh * 60 + em) - (sh * 60 + sm)


def add_minutes(time_str: str, minutes: int) -> str:
    h, m = map(int, time_str.split(":"))
    total = h * 60 + m + minutes
    return f"{(total // 60) % 24:02d}:{total % 60:02d}"


def random_evening_start() -> str:
    return f"{random.randint(16, 18):02d}:00"


def random_float(min_v, max_v):
    return random.uniform(min_v, max_v)


def generate_bitstring(length: int, rate: float) -> str:
    return "".join("1" if random.random() < rate else "0" for _ in range(length))


def is_overlap(start1, end1, start2, end2):
    return start1 < end2 and start2 < end1


#conflict checker
async def has_conflict(teacher, date, start, end, ignore_exception_id=None):

    #check exception sessions
    exceptions = await ExceptionSession.find(
        ExceptionSession.teacher == teacher,
        ExceptionSession.date == date
    ).to_list()

    for e in exceptions:
        if ignore_exception_id and e.id == ignore_exception_id:
            continue

        if e.start_time and e.end_time:
            if is_overlap(start, end, e.start_time, e.end_time):
                return True

    #check normal sessions
    sessions = await Session.find(
        Session.teacher.id == teacher.id,
        Session.day == date.strftime("%A")
    ).to_list()

    for s in sessions:
        if is_overlap(start, end, s.start_time, s.end_time):
            return True

    return False


#attendance check
async def attendance_exists(session, exception, date):
    if exception:
        return await Attendance.find_one(
            Attendance.date == date,
            Attendance.exception_session.id == exception.id
        ) is not None

    return await Attendance.find_one(
        Attendance.date == date,
        Attendance.session.id == session.id
    ) is not None


#main
async def run():
    await init_db()

    students = await Student.find().to_list()
    sessions = await Session.find(fetch_links=True).to_list()

    if not students or not sessions:
        print("Base data missing")
        return

    sessions_by_day = {}
    for s in sessions:
        sessions_by_day.setdefault(s.day, []).append(s)

    date_cursor = START_DATE

    while date_cursor <= END_DATE:

        weekday = WEEKDAYS[date_cursor.weekday()]
        todays_sessions = sessions_by_day.get(weekday, [])

        for sess in todays_sessions:

            if not sess.teacher:
                continue

            roll = random.random()
            target_date = date_cursor
            exception = None

            #CANCEL
            if roll < CANCEL_PROB:
                await ExceptionSession(
                    session=sess,
                    action="Cancel",
                    reason="Auto generated cancel",
                    date=target_date,
                    created_by=sess.teacher,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                ).insert()
                continue

            #RESCHEDULE
            elif roll < CANCEL_PROB + RESCHEDULE_PROB:

                duration = time_diff_minutes(sess.start_time, sess.end_time)

                for _ in range(5):

                    new_date = target_date + timedelta(days=random.randint(1, 7))
                    new_start = random_evening_start()
                    new_end = add_minutes(new_start, duration)

                    if not await has_conflict(sess.teacher, new_date, new_start, new_end):

                        exception = ExceptionSession(
                            session=sess,
                            subject=sess.subject,
                            teacher=sess.teacher,
                            action="Reschedule",
                            reason="Auto generated reschedule",
                            date=new_date,
                            start_time=new_start,
                            end_time=new_end,
                            swap_role="SOURCE",
                            created_by=sess.teacher,
                            created_at=datetime.utcnow(),
                            updated_at=datetime.utcnow()
                        )
                        await exception.insert()
                        target_date = new_date
                        break

                #swap
                if exception and random.random() < SWAP_PROB and len(todays_sessions) > 1:

                    target = next(
                        (s for s in todays_sessions if s.id != sess.id),
                        None
                    )

                    if target and target.teacher:

                        status = "REJECTED" if random.random() < SWAP_REJECT_PROB else "APPROVED"

                        swap = SwapApproval(
                            exception=exception,
                            source_session=sess,
                            target_session=target,
                            requested_by=sess.teacher,
                            requested_to=target.teacher,
                            status=status,
                            created_at=datetime.utcnow(),
                            responded_at=datetime.utcnow()
                        )
                        await swap.insert()

                        exception.swap_id = swap
                        await exception.save()

                        if status == "APPROVED":

                            target_start = sess.start_time
                            target_end = sess.end_time

                            conflict = await has_conflict(
                                target.teacher,
                                target_date,
                                target_start,
                                target_end
                            )

                            if not conflict:

                                target_exception = ExceptionSession(
                                    session=target,
                                    subject=target.subject,
                                    teacher=target.teacher,
                                    action="Reschedule",
                                    reason="Swap approved",
                                    date=target_date,
                                    start_time=target_start,
                                    end_time=target_end,
                                    swap_id=swap,
                                    swap_role="TARGET",
                                    created_by=target.teacher,
                                    created_at=datetime.utcnow(),
                                    updated_at=datetime.utcnow()
                                )
                                await target_exception.insert()

                                #create attendance for target swap
                                if not await attendance_exists(target, target_exception, target_date):
                                    att = Attendance(
                                        session=None,
                                        exception_session=target_exception,
                                        date=target_date,
                                        students="",
                                        created_at=datetime.utcnow(),
                                        updated_at=datetime.utcnow()
                                    )
                                    await att.insert()

                                    att.students = generate_bitstring(len(students), random_float(0.6, 0.9))
                                    await att.save()

            #ADD SESSION
            elif roll < CANCEL_PROB + RESCHEDULE_PROB + ADD_SESSION_PROB:

                duration = time_diff_minutes(sess.start_time, sess.end_time)

                for _ in range(5):

                    new_start = add_minutes(sess.end_time, random.choice([60, 120]))
                    new_end = add_minutes(new_start, duration)

                    if not await has_conflict(sess.teacher, target_date, new_start, new_end):

                        exception = ExceptionSession(
                            session=None,
                            subject=sess.subject,
                            teacher=sess.teacher,
                            action="Add",
                            reason="Auto generated extra lecture",
                            date=target_date,
                            start_time=new_start,
                            end_time=new_end,
                            created_by=sess.teacher,
                            created_at=datetime.utcnow(),
                            updated_at=datetime.utcnow()
                        )
                        await exception.insert()
                        break

            #ATTENDANCE
            if await attendance_exists(sess, exception, target_date):
                continue

            attendance = Attendance(
                session=None if exception else sess,
                exception_session=exception,
                date=target_date,
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