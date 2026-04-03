import logging
from bson import ObjectId
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta
from fastapi import Request
from fastapi.responses import JSONResponse

from app.models.allModel import (
    CreateExceptionSession,
    NotificationRequest,
    TakeSwapActionRequest,
)

from app.schemas.exception_session import ExceptionSession
from app.schemas.swap_approval import SwapApproval
from app.schemas.session import Session
from app.schemas.teacher import Teacher

from app.services.common_services.notify_users import notify_users
from app.utils.notify import notify_students_by_session, notify_students_for_two_sessions
from app.utils.parse_data import enqueue_exception_session, overlap_error_response
from app.core.redis import redis_client


logger = logging.getLogger("session_exception")
logger.setLevel(logging.INFO)

IST = ZoneInfo("Asia/Kolkata")

REDIS_SESSION_JOB_PREFIX = "attendance:job:"


async def create_session_exception(
    request: Request,
    exception_request: CreateExceptionSession
):

    logger.info("create_session_exception called")

    user = request.state.user

    if user.get("role") != "teacher":
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Only teachers allowed"}
        )

    requester = await Teacher.get(ObjectId(user["id"]))

    if not requester:
        return JSONResponse(
            status_code=404,
            content={"success": False, "message": "Teacher not found"}
        )

    action = exception_request.action
    ex_date = exception_request.date
    day_name = ex_date.strftime("%A")
    confirm_swap = bool(exception_request.confirm_swap)

    if ex_date < datetime.now(IST).date():
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Cannot create exception for past date"}
        )

    # --------------------------------------------------
    # CANCEL
    # --------------------------------------------------

    if action == "Cancel":

        if not exception_request.session_id:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "session_id required for cancel"}
            )

        session_obj = await Session.get(
            exception_request.session_id,
            Session.is_active == True,
            fetch_links=True
        )

        #check if session already started
        now = datetime.now(IST)

        session_start_dt = datetime.strptime(
            f"{ex_date} {session_obj.start_time}",
            "%Y-%m-%d %H:%M"
        ).replace(tzinfo=IST)

        if now >= session_start_dt:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "message": "Cannot cancel session that has already started or completed"
                }
            )

        if not session_obj:
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": "Session not found"}
            )

        if str(session_obj.teacher.id) != str(requester.id):
            return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "message": "You cannot cancel this session"
                }
            )

        existing = await ExceptionSession.find_one(
            ExceptionSession.session.id == session_obj.id,
            ExceptionSession.date == ex_date,
            ExceptionSession.action == "Cancel"
        )

        if existing:
            return JSONResponse(
                status_code=409,
                content={
                    "success": False,
                    "message": "Session already cancelled"
                }
            )

        cancel_exception = ExceptionSession(
            session=session_obj,
            teacher=requester,
            subject=session_obj.subject,
            date=ex_date,
            action="Cancel",
            reason=exception_request.reason,
            created_by=requester
        )

        await cancel_exception.insert()

        redis_key = f"{REDIS_SESSION_JOB_PREFIX}{session_obj.id}:{ex_date}"
        await redis_client.delete(redis_key)

        return JSONResponse(
            status_code=201,
            content={
                "success": True,
                "message": "Session cancelled successfully",
                "data": {"exception_id": str(cancel_exception.id)}
            }
        )

    # --------------------------------------------------
    # VALIDATE TIME
    # --------------------------------------------------

    if not exception_request.new_start_time or not exception_request.new_end_time:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "new_start_time and new_end_time required"}
        )

    start_time = exception_request.new_start_time
    end_time = exception_request.new_end_time

    start_dt = datetime.strptime(start_time, "%H:%M")
    end_dt = datetime.strptime(end_time, "%H:%M")

    if end_dt <= start_dt:
        return JSONResponse(
            status_code=400,
            content={
            "success": False,
            "message": "End time must be greater than start time"
        }
    )

    # --------------------------------------------------
    # ADD
    # --------------------------------------------------

    if action == "Add":

        session_obj = None

        if exception_request.session_id:
            session_obj = await Session.get(
                exception_request.session_id,
                fetch_links=True
            )

        elif exception_request.subject_id:

            session_obj = await Session.find_one(
                Session.subject.id == ObjectId(exception_request.subject_id),
                Session.teacher.id == requester.id,
                fetch_links=True
            )

            if not session_obj:
                return JSONResponse(
                    status_code=404,
                    content={"success": False, "message": "Subject not assigned to teacher"}
                )

        if not session_obj:
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": "Session not found"}
            )

        overlapping_sessions = await Session.find(
            Session.day == day_name,
            Session.start_time < end_time,
            Session.end_time > start_time,
            Session.teacher.id == requester.id,
            fetch_links=True
        ).to_list()

        if len(overlapping_sessions) == 0:

            add_exception = ExceptionSession(
                session=session_obj,
                teacher=requester,
                subject=session_obj.subject,
                date=ex_date,
                action="Add",
                reason=exception_request.reason,
                start_time=start_time,
                end_time=end_time,
                created_by=requester
            )

            await add_exception.insert()

            await enqueue_exception_session(
                session=session_obj,
                exception=add_exception,
                date=ex_date,
                start_time=start_time
            )

            await notify_students_by_session(
                session=session_obj,
                title="Extra Lecture Added",
                message=f"Extra lecture scheduled {start_time}-{end_time}"
            )

            return JSONResponse(
                status_code=201,
                content={
                    "success": True,
                    "message": "Extra lecture added successfully",
                    "data": {"exception_id": str(add_exception.id)}
                }
            )

        if len(overlapping_sessions) > 1:
            return overlap_error_response(len(overlapping_sessions))

        target = overlapping_sessions[0]

        if not confirm_swap:

            return JSONResponse(
                status_code=409,
                content={
                    "success": False,
                    "code": "OVERLAP_FOUND",
                    "data": {
                        "can_swap": True,
                        "conflicting_teacher": f"{target.teacher.first_name} {target.teacher.last_name}",
                        "conflicting_session_id": str(target.id),
                        "time": f"{target.start_time}-{target.end_time}",
                    }
                }
            )

        add_exception = ExceptionSession(
            session=session_obj,
            teacher=requester,
            subject=session_obj.subject,
            date=ex_date,
            action="Add",
            reason=exception_request.reason,
            start_time=start_time,
            end_time=end_time,
            created_by=requester,
            swap_role="SOURCE"
        )

        await add_exception.insert()

        await enqueue_exception_session(
            session=session_obj,
            exception=add_exception,
            date=ex_date,
            start_time=start_time
        )

        swap = SwapApproval(
            exception=add_exception,
            source_session=session_obj,
            target_session=target,
            requested_by=requester,
            requested_to=target.teacher,
            status="PENDING"
        )

        await swap.insert()

        add_exception.swap_id = swap
        await add_exception.save()

        await notify_users(
            NotificationRequest(
                user="teacher",
                target_ids=[str(target.teacher.id)],
                title="Extra Lecture Swap Request",
                message="Swap request received",
                data={"route": f"/teacher/request/{add_exception.id}"}
            )
        )

        return JSONResponse(
            status_code=201,
            content={
                "success": True,
                "message": "Swap request sent",
                "data": {"swap_id": str(swap.id)}
            }
        )

    # --------------------------------------------------
    # RESCHEDULE
    # --------------------------------------------------

    if not exception_request.session_id:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "session_id required"}
        )

    session_obj = await Session.get(
        exception_request.session_id,
        fetch_links=True
    )

    #check if session already started
    now = datetime.now(IST)

    session_start_dt = datetime.strptime(
        f"{ex_date} {session_obj.start_time}",
        "%Y-%m-%d %H:%M"
    ).replace(tzinfo=IST)

    if now >= session_start_dt:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "Cannot reschedule session that has already started or completed"
            }
        )

    if not session_obj:
        return JSONResponse(
            status_code=404,
            content={"success": False, "message": "Session not found"}
        )

    if str(session_obj.teacher.id) != str(requester.id):
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "You cannot reschedule this session"}
        )

    overlapping_sessions = await Session.find(
        Session.day == day_name,
        Session.start_time < end_time,
        Session.end_time > start_time,
        Session.teacher.id != requester.id,
        fetch_links=True
    ).to_list()

    if len(overlapping_sessions) > 1:
        return overlap_error_response(len(overlapping_sessions))

    if len(overlapping_sessions) == 1 and not confirm_swap:

        target = overlapping_sessions[0]

        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "code": "OVERLAP_FOUND",
                "data": {
                    "can_swap": True,
                    "conflicting_teacher": f"{target.teacher.first_name} {target.teacher.last_name}",
                    "conflicting_session_id": str(target.id),
                }
            }
        )

    source_exception = ExceptionSession(
        session=session_obj,
        teacher=requester,
        subject=session_obj.subject,
        date=ex_date,
        action="Reschedule",
        reason=exception_request.reason,
        start_time=start_time,
        end_time=end_time,
        created_by=requester,
        swap_role="SOURCE"
    )

    await source_exception.insert()

    redis_key = f"{REDIS_SESSION_JOB_PREFIX}{session_obj.id}:{ex_date}"
    await redis_client.delete(redis_key)

    if len(overlapping_sessions) == 0:

        await enqueue_exception_session(
            session=session_obj,
            exception=source_exception,
            date=ex_date,
            start_time=start_time
        )

        await notify_students_by_session(
            session=session_obj,
            title="Timing Updated",
            message=f"New timing {start_time}-{end_time}"
        )

        return JSONResponse(
            status_code=201,
            content={
                "success": True,
                "message": "Session rescheduled",
                "data": {"exception_id": str(source_exception.id)}
            }
        )

    target = overlapping_sessions[0]

    swap = SwapApproval(
        exception=source_exception,
        source_session=session_obj,
        target_session=target,
        requested_by=requester,
        requested_to=target.teacher,
        status="PENDING"
    )

    await swap.insert()

    source_exception.swap_id = swap
    await source_exception.save()

    await notify_users(
        NotificationRequest(
            user="teacher",
            target_ids=[str(target.teacher.id)],
            title="Session Swap Request",
            message="Swap request received",
            data={"route": f"/teacher/request/{source_exception.id}"}
        )
    )

    return JSONResponse(
        status_code=201,
        content={
            "success": True,
            "message": "Swap request sent",
            "data": {"swap_id": str(swap.id)}
        }
    )

# --------------------------------------------------
# TAKE SWAP ACTION
# --------------------------------------------------

async def take_action_session_exception(
    request: Request,
    payload: TakeSwapActionRequest
):
    logger.info("take_action_session_exception called")

    user = request.state.user
    if user.get("role") != "teacher":
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Only teachers allowed"}
        )

    swap = await SwapApproval.get(
        ObjectId(payload.swap_id),
        fetch_links=True
    )
    if not swap:
        return JSONResponse(
            status_code=404,
            content={"success": False, "message": "Swap not found"}
        )

    if str(swap.requested_to.id) != user["id"]:
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Unauthorized"}
        )

    if swap.status != "PENDING":
        return JSONResponse(
            status_code=409,
            content={"success": False, "message": "Already processed"}
        )

    if payload.action == "REJECT":
        swap.status = "REJECTED"
        swap.responded_at = datetime.utcnow()
        await swap.save()

        await notify_users(
            NotificationRequest(
                user="teacher",
                target_ids=[str(swap.requested_by.id)],
                title="Swap Rejected",
                message="Your swap request was rejected",
            )
        )

        return JSONResponse(
            status_code=200,
            content={"success": True, "message": "Swap rejected"}
        )

    # APPROVED
    swap.status = "APPROVED"
    swap.responded_at = datetime.utcnow()
    await swap.save()

    source_exception = swap.exception
    source_session = swap.source_session
    target_session = swap.target_session

    # swap timings
    source_start = source_session.start_time
    source_end = source_session.end_time

    source_exception.start_time = target_session.start_time
    source_exception.end_time = target_session.end_time
    await source_exception.save()

    target_exception = ExceptionSession(
        session=target_session,
        date=source_exception.date,
        action="Reschedule",
        reason="Swap approved",
        start_time=source_start,
        end_time=source_end,
        created_by=swap.requested_to,
        swap_id=swap,
        swap_role="TARGET"
    )
    await target_exception.insert()

    # enqueue BOTH sessions
    await enqueue_exception_session(
        session=source_session,
        exception=source_exception,
        date=source_exception.date,
        start_time=source_exception.start_time
    )

    await enqueue_exception_session(
        session=target_session,
        exception=target_exception,
        date=target_exception.date,
        start_time=target_exception.start_time
    )

    await notify_students_for_two_sessions(
        source_session,
        target_session,
        title="Session Timing Updated",
        message="Your session timing has been updated"
    )

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "Swap approved and applied",
            "data": {"swap_id": str(swap.id)}
        }
    )
