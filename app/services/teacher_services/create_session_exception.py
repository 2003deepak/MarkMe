from fastapi import Request
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import uuid

from app.models.allModel import CreateExceptionSession
from app.schemas.exception_session import ExceptionSession
from app.schemas.session import Session
from app.schemas.subject import Subject
from app.schemas.teacher import Teacher
from app.core.redis import redis_client
from app.utils.publisher import send_to_queue

REDIS_SESSION_JOB_PREFIX = "attendance:job:"
SESSION_QUEUE_NAME = "session_queue"


async def create_session_exception(request: Request, exception_request: CreateExceptionSession):
    # ---------------- AUTH ----------------
    if request.state.user.get("role") != "teacher":
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Only teachers can create exceptions"}
        )

    teacher_id = request.state.user.get("id")
    action = exception_request.action
    ex_date = exception_request.date
    date_str = ex_date.strftime("%Y-%m-%d")

    session_obj = None
    subject_obj = None

    # ---------------- FETCH BASE ENTITIES ----------------
    if action in ["Cancel", "Rescheduled"]:
        if not exception_request.session_id:
            return JSONResponse(status_code=400, content={"success": False, "message": "session_id required"})

        session_obj = await Session.get(exception_request.session_id, fetch_links=True)
        if not session_obj:
            return JSONResponse(status_code=404, content={"success": False, "message": "Session not found"})

    if action == "Add":
        if not exception_request.subject_id:
            return JSONResponse(status_code=400, content={"success": False, "message": "subject_id required for Add"})

        subject_obj = await Subject.get(exception_request.subject_id)
        teacher_obj = await Teacher.get(teacher_id)

        if not subject_obj or not teacher_obj:
            return JSONResponse(status_code=404, content={"success": False, "message": "Invalid subject/teacher"})

    # ---------------- CREATE EXCEPTION ----------------
    exception_doc = ExceptionSession(
        session=session_obj,
        subject=subject_obj if action == "Add" else None,
        teacher=teacher_obj if action == "Add" else None,
        date=ex_date,
        action=action,
        start_time=exception_request.new_start_time if action in ["Add", "Rescheduled"] else None,
        end_time=exception_request.new_end_time if action in ["Add", "Rescheduled"] else None,
    )
    await exception_doc.insert()

    # ---------------- REDIS KEY ----------------
    redis_key = (
        f"{REDIS_SESSION_JOB_PREFIX}{exception_doc.id}:{date_str}"
        if action == "Add"
        else f"{REDIS_SESSION_JOB_PREFIX}{session_obj.id}:{date_str}"
    )

    # ---------------- CANCEL ----------------
    if action == "Cancel":
        await redis_client.delete(redis_key)

    # ---------------- RESCHEDULE ----------------
    elif action == "Rescheduled":
        await redis_client.delete(redis_key)

        new_start = datetime.combine(
            ex_date,
            datetime.strptime(exception_request.new_start_time, "%H:%M").time()
        ).replace(tzinfo=ZoneInfo("Asia/Kolkata"))

        job_id = str(uuid.uuid4())
        await redis_client.set(redis_key, job_id, ex=48 * 3600)

        payload = {
            "session_id": str(session_obj.id),
            "subject": str(session_obj.subject.id),
            "date": date_str,
            "start_time_timestamp": new_start.timestamp(),
            "job_id": job_id,
            "is_exception": True,
            "exception_id": str(exception_doc.id)
        }

        delay = (new_start - timedelta(minutes=15) - datetime.now(ZoneInfo("Asia/Kolkata"))).total_seconds()
        await send_to_queue(SESSION_QUEUE_NAME, payload, delay_ms=max(0, int(delay * 1000)))

    # ---------------- ADD ----------------
    elif action == "Add":
        new_start = datetime.combine(
            ex_date,
            datetime.strptime(exception_request.new_start_time, "%H:%M").time()
        ).replace(tzinfo=ZoneInfo("Asia/Kolkata"))

        job_id = str(uuid.uuid4())
        await redis_client.set(redis_key, job_id, ex=48 * 3600)

        payload = {
            "subject": str(subject_obj.id),
            "teacher": teacher_id,
            "date": date_str,
            "start_time_timestamp": new_start.timestamp(),
            "job_id": job_id,
            "is_exception": True,
            "exception_id": str(exception_doc.id)
        }

        delay = (new_start - timedelta(minutes=15) - datetime.now(ZoneInfo("Asia/Kolkata"))).total_seconds()
        await send_to_queue(SESSION_QUEUE_NAME, payload, delay_ms=max(0, int(delay * 1000)))

    # ---------------- RESPONSE ----------------
    return JSONResponse(
        status_code=201,
        content={
            "success": True,
            "message": "Exception created",
            "exception_id": str(exception_doc.id),
            "action": action
        }
    )
