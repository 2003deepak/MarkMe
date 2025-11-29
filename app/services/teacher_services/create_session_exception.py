from fastapi import Request
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import uuid

from app.models.allModel import CreateExceptionSession
from app.schemas.exception_session import ExceptionSession
from app.schemas.session import Session
from app.core.redis import redis_client
from app.utils.publisher import send_to_queue

REDIS_SESSION_JOB_PREFIX = "attendance:job:"
SESSION_QUEUE_NAME = "session_queue"


async def create_session_exception(request: Request, exception_request: CreateExceptionSession):
    # ---------------- ROLE CHECK ----------------
    user_role = request.state.user.get("role")
    if user_role != "teacher":
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Only teachers are authorized to create session exceptions"}
        )

    action = exception_request.action
    ex_date = exception_request.date
    date_str = ex_date.strftime("%Y-%m-%d")

    # ---------------- FETCH SESSION ----------------
    session_obj = None
    if action in ["Cancel", "Rescheduled", "Add"]:
        if not exception_request.session_id:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "session_id is required for Cancel, Rescheduled, Add"}
            )

        # IMPORTANT: fetch_links=True (you requested this)
        session_obj = await Session.get(exception_request.session_id, fetch_links=True)

        if not session_obj:
            return JSONResponse(status_code=404, content={"success": False, "message": "Session not found"})

    # ---------------- VALIDATE TIMINGS ----------------
    if action in ["Add", "Rescheduled"]:
        if not (exception_request.new_start_time and exception_request.new_end_time):
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "new_start_time and new_end_time required"}
            )

    # ---------------- CREATE EXCEPTION DOC ----------------
    exception_doc = ExceptionSession(
        session=session_obj,
        date=ex_date,
        action=action,
        start_time=exception_request.new_start_time if action in ["Add", "Rescheduled"] else None,
        end_time=exception_request.new_end_time if action in ["Add", "Rescheduled"] else None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    await exception_doc.insert()

    # ---------------- REDIS KEY ----------------
    redis_key = f"{REDIS_SESSION_JOB_PREFIX}{str(session_obj.id)}:{date_str}"

    # ---------------- ACTION: CANCEL ----------------
    if action == "Cancel":
        await redis_client.delete(redis_key)

    # ---------------- ACTION: RESCHEDULE ----------------
    elif action == "Rescheduled":
        await redis_client.delete(redis_key)

        new_start_datetime = datetime.combine(
            ex_date,
            datetime.strptime(exception_request.new_start_time, "%H.%M").time()
        ).replace(tzinfo=ZoneInfo("Asia/Kolkata"))

        new_job_id = str(uuid.uuid4())
        await redis_client.set(redis_key, new_job_id, ex=48 * 3600)

        # subject is fully fetched → directly use session_obj.subject.id
        subject_id = str(session_obj.subject.id)

        payload = {
            "session_id": str(session_obj.id),
            "date": date_str,
            "day": new_start_datetime.strftime("%A"),
            "start_time_timestamp": new_start_datetime.timestamp(),
            "subject": subject_id,
            "job_id": new_job_id,
            "is_exception": True,
            "exception_id": str(exception_doc.id),
        }

        delay_seconds = (
            new_start_datetime - timedelta(minutes=15) -
            datetime.now(tz=ZoneInfo("Asia/Kolkata"))
        ).total_seconds()

        await send_to_queue(SESSION_QUEUE_NAME, payload, delay_ms=max(0, int(delay_seconds * 1000)))

    # ---------------- ACTION: ADD ----------------
    elif action == "Add":

        new_start_datetime = datetime.combine(
            ex_date,
            datetime.strptime(exception_request.new_start_time, "%H:%M").time()
        ).replace(tzinfo=ZoneInfo("Asia/Kolkata"))

        new_job_id = str(uuid.uuid4())
        await redis_client.set(redis_key, new_job_id, ex=48 * 3600)

        subject_id = str(session_obj.subject.id)

        session_payload = {
            "session_id": str(session_obj.id),
            "date": date_str,
            "day": new_start_datetime.strftime("%A"),
            "start_time_timestamp": new_start_datetime.timestamp(),
            "subject": subject_id,
            "job_id": new_job_id,
            "is_exception": True,
            "exception_id": str(exception_doc.id)
        }

        delay_seconds = (
            new_start_datetime - timedelta(minutes=15) -
            datetime.now(tz=ZoneInfo("Asia/Kolkata"))
        ).total_seconds()

        await send_to_queue(SESSION_QUEUE_NAME, session_payload, delay_ms=max(0, int(delay_seconds * 1000)))

    # ---------------- RESPONSE ----------------
    return JSONResponse(
        status_code=201,
        content={
            "success": True,
            "message": "Exception created and scheduling updated",
            "data": {
                "exception_id": str(exception_doc.id),
                "action": exception_doc.action,
                "date": date_str,
                "session_id": str(session_obj.id) if session_obj else None,
                "start_time": exception_doc.start_time,
                "end_time": exception_doc.end_time,
                "created_at": exception_doc.created_at.isoformat(),
                "updated_at": exception_doc.updated_at.isoformat(),
            }
        }
    )
