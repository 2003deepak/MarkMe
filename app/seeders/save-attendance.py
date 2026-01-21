import asyncio
import random
from datetime import datetime, timedelta

from core.database import init_db
from schemas.session import Session
from schemas.exception_session import ExceptionSession
from schemas.attendance import Attendance
from schemas.student import Student

# probabilities
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

# ---------------- helpers ---------------- #

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


# ---------------- main ---------------- #

async def run():
    await init_db()

    students = await Student.find().to_list()
    sessions = await Session.find(fetch_links=True).to_list()

    if not students or not sessions:
        print("❌ Base data missing")
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

            # ---------------- CANCEL ---------------- #
            if roll < CANCEL_PROB:
                exception = ExceptionSession(
                    session=sess,
                    action="Cancel",
                    reason="Auto generated cancel",
                    date=target_date,
                    created_by=sess.teacher,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                await exception.insert()
                continue

            # ---------------- RESCHEDULE ---------------- #
            elif roll < CANCEL_PROB + RESCHEDULE_PROB:
                duration = time_diff_minutes(sess.start_time, sess.end_time)
                new_date = target_date + timedelta(days=random.randint(1, 7))
                new_start = random_evening_start()
                new_end = add_minutes(new_start, duration)

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

                # -------- SWAP -------- #
                if random.random() < SWAP_PROB and len(todays_sessions) > 1:
                    target = next(
                        (s for s in todays_sessions if s.id != sess.id),
                        None
                    )

                    if target and target.teacher:
                        status = "REJECTED" if random.random() < SWAP_REJECT_PROB else "APPROVED"

                        from schemas.swap_approval import SwapApproval

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
                            await ExceptionSession(
                                session=target,
                                action="Reschedule",
                                reason="Swap approved",
                                date=new_date,
                                start_time=sess.start_time,
                                end_time=sess.end_time,
                                swap_id=swap,
                                swap_role="TARGET",
                                created_by=target.teacher,
                                created_at=datetime.utcnow(),
                                updated_at=datetime.utcnow()
                            ).insert()

            # ---------------- ADD SESSION ---------------- #
            elif roll < CANCEL_PROB + RESCHEDULE_PROB + ADD_SESSION_PROB:
                exception = ExceptionSession(
                    session=None,
                    subject=sess.subject,
                    teacher=sess.teacher,
                    action="Add",
                    reason="Auto generated extra lecture",
                    date=target_date,
                    start_time=sess.start_time,
                    end_time=sess.end_time,
                    created_by=sess.teacher,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                await exception.insert()

            # ---------------- ATTENDANCE ---------------- #
            attendance = Attendance(
                session=None if exception else sess,
                exception_session=exception,
                date=target_date,
                students="",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            await attendance.insert()

            bitstring = generate_bitstring(
                len(students),
                random_float(0.6, 0.9)
            )

            attendance.students = bitstring
            await attendance.save()

        date_cursor += timedelta(days=1)

    print("✅ Seeding completed successfully")


if __name__ == "__main__":
    asyncio.run(run())
