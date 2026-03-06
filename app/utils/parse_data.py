from typing import List, Optional
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta, timezone

from fastapi.responses import JSONResponse
import uuid
from app.utils.publisher import send_to_queue
from app.core.redis import redis_client


def parse_comma_separated_list(value: Optional[str]) -> Optional[List[str]]:
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]

def overlap_error_response(count: int):
    return JSONResponse(
        status_code=409,
        content={
            "success": False,
            "code": "MULTIPLE_OVERLAPS",
            "message": (
                f"Session overlaps with {count} existing sessions. "
                "Swap is allowed only when overlapping with exactly one session."
            )
        }
    )


IST = ZoneInfo("Asia/Kolkata")

def to_ist(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST)


REDIS_SESSION_JOB_PREFIX = "attendance:job:"
SESSION_QUEUE_NAME = "session_queue"


async def enqueue_exception_session(
    *,
    session,
    exception,
    start_time: str,
    date,
):
    date_str = str(date)

    start_dt = datetime.strptime(
        f"{date_str} {start_time}",
        "%Y-%m-%d %H:%M"
    ).replace(tzinfo=IST)

    delay = (start_dt - timedelta(minutes=15) - datetime.now(tz=IST)).total_seconds()
    if delay <= 0:
        delay = 1  # run immediately

    job_id = str(uuid.uuid4())

    redis_key = f"{REDIS_SESSION_JOB_PREFIX}{session.id}:{date_str}"
    await redis_client.set(redis_key, job_id, ex=48 * 3600)

    payload = {
        "session_id": str(session.id),
        "date": date_str,
        "day": start_dt.strftime("%A"),
        "start_time_timestamp": start_dt.timestamp(),
        "subject": str(session.subject.id),
        "program": session.program,
        "department": session.department,
        "semester": session.semester,
        "academic_year": session.academic_year,
        "job_id": job_id,
        "is_exception": True,
        "exception_id": str(exception.id),
    }
    
    print("Session added in queue with delay ms :- " + (delay*1000))

    await send_to_queue(
        SESSION_QUEUE_NAME,
        payload,
        delay_ms=int(delay * 1000)
    )
    


def validate_student_academic(user):
    fields = {
        "program": user.get("program"),
        "department": user.get("department"),
        "semester": user.get("semester"),
        "academic_year": user.get("batch_year")
    }
    missing = [k for k, v in fields.items() if not v]
    return missing

