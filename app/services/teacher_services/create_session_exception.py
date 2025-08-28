from fastapi import APIRouter, HTTPException
from datetime import datetime, timedelta, date as DateType
from zoneinfo import ZoneInfo
import uuid

from app.schemas.exception_session import ExceptionSession
from app.schemas.session import Session
from app.core.redis import redis_client
from app.utils.publisher import send_to_queue

REDIS_SESSION_JOB_PREFIX = "attendance:job:"
SESSION_QUEUE_NAME = "session_queue"

async def create_session_exception(request, user_data):
    # Validate user role
    if user_data["role"] != "teacher":
        raise HTTPException(
            status_code=403,
            detail="Only teachers are authorized to create session exceptions"
        )

    action = request.action
    ex_date = request.date
    date_str = ex_date.strftime("%Y-%m-%d")

    # Fetch session document if required (Cancel / Rescheduled)
    session_obj = None
    if action in ["Cancel", "Rescheduled"]:
        if not request.session_id:
            raise HTTPException(400, "session_id is required for Cancel and Rescheduled actions")
        session_obj = await Session.get(request.session_id)
        if not session_obj:
            raise HTTPException(404, "Session not found")

    # Validate start_time and end_time for Add or Rescheduled
    if action in ["Add", "Rescheduled"]:
        if not (request.start_time and request.end_time):
            raise HTTPException(400, "startTime and endTime required for Add and Rescheduled actions")

    # Build ExceptionSession document
    exception_doc = ExceptionSession(
        session=session_obj,
        date=ex_date,
        action=action,
        start_time=request.start_time if action in ["Add", "Rescheduled"] else None,
        end_time=request.end_time if action in ["Add", "Rescheduled"] else None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    await exception_doc.insert()

    # Redis key for this session and date
    if session_obj:
        redis_key = f"{REDIS_SESSION_JOB_PREFIX}{str(session_obj.id)}:{date_str}"
    else:
        # For Add action where no session linked yet, create surrogate key
        redis_key = f"{REDIS_SESSION_JOB_PREFIX}new_{str(exception_doc.id)}:{date_str}"

    # Action-specific Redis and queue logic
    if action == "Cancel":
        # Delete Redis key to invalidate any scheduled job
        await redis_client.delete(redis_key)

    elif action == "Rescheduled":
        # Delete old Redis job key
        await redis_client.delete(redis_key)

        # Schedule new job with new start time
        new_start_datetime = datetime.combine(ex_date, datetime.strptime(request.start_time, "%H:%M").time())
        new_start_datetime = new_start_datetime.replace(tzinfo=ZoneInfo("Asia/Kolkata"))

        new_job_id = str(uuid.uuid4())
        expiration_seconds = 48 * 3600  # 2 days TTL for Redis key
        await redis_client.set(redis_key, new_job_id, ex=expiration_seconds)

        # Prepare job payload
        payload = {
            "session_id": str(session_obj.id),
            "date": date_str,
            "day": new_start_datetime.strftime("%A"),
            "start_time_timestamp": new_start_datetime.timestamp(),
            "subject": str(session_obj.subject.id) if hasattr(session_obj.subject, "id") else str(session_obj.subject),
            "program": session_obj.program,
            "department": session_obj.department,
            "semester": session_obj.semester,
            "academic_year": session_obj.academic_year,
            "job_id": new_job_id,
        }
        delay_seconds = (new_start_datetime - timedelta(minutes=15) - datetime.now(tz=ZoneInfo("Asia/Kolkata"))).total_seconds()
        await send_to_queue(SESSION_QUEUE_NAME, payload, delay_ms=max(0, int(delay_seconds * 1000)))

    elif action == "Add":
        # Schedule new job for the added session
        new_start_datetime = datetime.combine(ex_date, datetime.strptime(request.start_time, "%H:%M").time())
        new_start_datetime = new_start_datetime.replace(tzinfo=ZoneInfo("Asia/Kolkata"))

        new_job_id = str(uuid.uuid4())
        expiration_seconds = 48 * 3600
        await redis_client.set(redis_key, new_job_id, ex=expiration_seconds)

        payload = {
            "session_id": f"new_{str(exception_doc.id)}",  # surrogate session id
            "date": date_str,
            "day": new_start_datetime.strftime("%A"),
            "start_time_timestamp": new_start_datetime.timestamp(),
            "subject": None,  # No subject for new session
            "program": None,
            "department": None,
            "semester": None,
            "academic_year": None,
            "job_id": new_job_id,
        }
        delay_seconds = (new_start_datetime - timedelta(minutes=15) - datetime.now(tz=ZoneInfo("Asia/Kolkata"))).total_seconds()
        await send_to_queue(SESSION_QUEUE_NAME, payload, delay_ms=max(0, int(delay_seconds * 1000)))

    return {
        "message": "Exception created and scheduling updated",
        "exception_id": str(exception_doc.id),
        "details": {
            "action": exception_doc.action,
            "date": date_str,
            "session_id": str(session_obj.id) if session_obj else None,
            "start_time": exception_doc.start_time,
            "end_time": exception_doc.end_time,
            "created_at": exception_doc.created_at.isoformat(),
            "updated_at": exception_doc.updated_at.isoformat()
        }
    }