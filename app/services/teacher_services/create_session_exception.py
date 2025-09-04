from fastapi import HTTPException
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import uuid
from bson import ObjectId, DBRef
from beanie.odm.fields import Link

from app.schemas.exception_session import ExceptionSession
from app.schemas.session import Session
from app.core.redis import redis_client
from app.utils.publisher import send_to_queue

REDIS_SESSION_JOB_PREFIX = "attendance:job:"
SESSION_QUEUE_NAME = "session_queue"


async def create_session_exception(request, user_data):
    # ✅ Role validation
    if user_data["role"] != "teacher":
        raise HTTPException(
            status_code=403,
            detail="Only teachers are authorized to create session exceptions"
        )

    action = request.action
    ex_date = request.date
    date_str = ex_date.strftime("%Y-%m-%d")

    # ✅ Fetch session if needed
    session_obj = None
    if action in ["Cancel", "Rescheduled"]:
        if not request.session_id:
            raise HTTPException(400, "session_id is required for Cancel and Rescheduled actions")

        session_obj = await Session.get(request.session_id)
        if not session_obj:
            raise HTTPException(404, "Session not found")

    # ✅ Validate timings
    if action in ["Add", "Rescheduled"]:
        if not (request.new_start_time and request.new_end_time):
            raise HTTPException(400, "new_start_time and new_end_time required for Add and Rescheduled actions")

    # ✅ Create ExceptionSession doc
    exception_doc = ExceptionSession(
        session=session_obj,
        date=ex_date,
        action=action,
        start_time=request.new_start_time if action in ["Add", "Rescheduled"] else None,
        end_time=request.new_end_time if action in ["Add", "Rescheduled"] else None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    await exception_doc.insert()

    # ✅ Redis key
    if session_obj:
        redis_key = f"{REDIS_SESSION_JOB_PREFIX}{str(session_obj.id)}:{date_str}"
    else:
        redis_key = f"{REDIS_SESSION_JOB_PREFIX}new_{str(exception_doc.id)}:{date_str}"

    # ---------- ACTION HANDLING ----------
    if action == "Cancel":
        # ❌ Just delete redis key
        await redis_client.delete(redis_key)

    elif action == "Rescheduled":
        # ❌ Remove old job
        await redis_client.delete(redis_key)

        # ✅ New datetime
        new_start_datetime = datetime.combine(
            ex_date, datetime.strptime(request.new_start_time, "%H.%M").time()
        ).replace(tzinfo=ZoneInfo("Asia/Kolkata"))

        # ✅ New Redis job
        new_job_id = str(uuid.uuid4())
        await redis_client.set(redis_key, new_job_id, ex=48 * 3600)

        # ✅ Subject extraction (normalize all cases)
        subject_id = None
        subj = session_obj.subject
        if isinstance(subj, DBRef):
            subject_id = str(subj.id)
        elif isinstance(subj, Link):
            subject_id = str(subj.ref.id)
        elif isinstance(subj, ObjectId):
            subject_id = str(subj)
        elif isinstance(subj, str):
            subject_id = subj
        elif hasattr(subj, "id"):
            subject_id = str(subj.id)
        else:
            raise HTTPException(400, f"Invalid subject format for session {str(session_obj.id)}")

        # ✅ Job payload
        payload = {
            "session_id": str(session_obj.id),
            "date": date_str,
            "day": new_start_datetime.strftime("%A"),
            "start_time_timestamp": new_start_datetime.timestamp(),
            "subject": subject_id,
            "program": session_obj.program,
            "department": session_obj.department,
            "semester": session_obj.semester,
            "academic_year": session_obj.academic_year,
            "job_id": new_job_id,
            "exception_id": str(exception_doc.id),
            "is_exception": True,
        }

        delay_seconds = (
            new_start_datetime - timedelta(minutes=15) - datetime.now(tz=ZoneInfo("Asia/Kolkata"))
        ).total_seconds()

        await send_to_queue(
            SESSION_QUEUE_NAME, payload, delay_ms=max(0, int(delay_seconds * 1000))
        )

    elif action == "Add":
        # ✅ New session job
        new_start_datetime = datetime.combine(
            ex_date, datetime.strptime(request.new_start_time, "%H.%M").time()
        ).replace(tzinfo=ZoneInfo("Asia/Kolkata"))

        new_job_id = str(uuid.uuid4())
        await redis_client.set(redis_key, new_job_id, ex=48 * 3600)

        payload = {
            "session_id": f"new_{str(exception_doc.id)}",  # surrogate
            "date": date_str,
            "day": new_start_datetime.strftime("%A"),
            "start_time_timestamp": new_start_datetime.timestamp(),
            "subject": None,
            "program": None,
            "department": None,
            "semester": None,
            "academic_year": None,
            "job_id": new_job_id,
            "exception_id": str(exception_doc.id),
            "is_exception": True,
        }

        delay_seconds = (
            new_start_datetime - timedelta(minutes=15) - datetime.now(tz=ZoneInfo("Asia/Kolkata"))
        ).total_seconds()

        await send_to_queue(
            SESSION_QUEUE_NAME, payload, delay_ms=max(0, int(delay_seconds * 1000))
        )

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
            "updated_at": exception_doc.updated_at.isoformat(),
        },
    }
