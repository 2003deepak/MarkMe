from bson import ObjectId
from datetime import datetime
from zoneinfo import ZoneInfo
import logging

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
from app.utils.parse_data import overlap_error_response

logger = logging.getLogger("session_exception")
logger.setLevel(logging.INFO)

IST = ZoneInfo("Asia/Kolkata")


async def create_session_exception(
    request: Request,
    exception_request: CreateExceptionSession
):
    logger.info("create_session_exception called")

    # auth
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

    # cancel
    if action == "Cancel":
        if not exception_request.session_id:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "session_id required for cancel"}
            )

        session_obj = await Session.get(
            exception_request.session_id,
            fetch_links=True
        )
        if not session_obj:
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": "Session not found"}
            )

        cancel_exception = ExceptionSession(
            session=session_obj,
            date=ex_date,
            action="Cancel",
            reason=exception_request.reason,
            created_by=requester
        )
        await cancel_exception.insert()

        return JSONResponse(
            status_code=201,
            content={
                "success": True,
                "message": "Session cancelled successfully",
                "data": {
                    "exception_id": str(cancel_exception.id)
                }
            }
        )

    # validation
    if not exception_request.new_start_time or not exception_request.new_end_time:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "new_start_time and new_end_time are required"
            }
        )

    start_time = exception_request.new_start_time
    end_time = exception_request.new_end_time

    # add
    if action == "Add":

        overlapping_sessions = await Session.find(
            Session.day == day_name,
            Session.start_time < end_time,
            Session.end_time > start_time,
            Session.department == requester.department,
            fetch_links=True
        ).to_list()

        overlap_count = len(overlapping_sessions)

        if overlap_count == 0:
            add_exception = ExceptionSession(
                session=None,
                date=ex_date,
                action="Add",
                reason=exception_request.reason,
                start_time=start_time,
                end_time=end_time,
                created_by=requester
            )
            await add_exception.insert()

            await notify_students_by_session(
                session=requester,
                title="New Extra Lecture Added",
                message=f"A new lecture is scheduled from {start_time} to {end_time}"
            )

            return JSONResponse(
                status_code=201,
                content={
                    "success": True,
                    "message": "Extra lecture added successfully",
                    "data": {"exception_id": str(add_exception.id)}
                }
            )

        if overlap_count > 1:
            return overlap_error_response(overlap_count)

        target = overlapping_sessions[0]

        if not confirm_swap:
            return JSONResponse(
                status_code=409,
                content={
                    "success": False,
                    "code": "OVERLAP_FOUND",
                    "message": "Extra lecture overlaps with another session",
                    "data": {
                        "can_swap": True,
                        "conflicting_teacher": f"{target.teacher.first_name} {target.teacher.last_name}",
                        "conflicting_session_id": str(target.id),
                        "time": f"{target.start_time}-{target.end_time}"
                    }
                }
            )

        add_exception = ExceptionSession(
            session=None,
            date=ex_date,
            action="Add",
            reason=exception_request.reason,
            start_time=start_time,
            end_time=end_time,
            created_by=requester,
            swap_role="SOURCE"
        )
        await add_exception.insert()

        swap = SwapApproval(
            exception=add_exception,
            source_session=None,
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
                message="You have received a swap request",
                data={
                    "route": f"/teacher/request/{str(add_exception.id)}",
                    "type": "SWAP_REQUEST"
                }
            )
        )

        return JSONResponse(
            status_code=201,
            content={
                "success": True,
                "message": "Swap request sent for approval",
                "data": {"swap_id": str(swap.id)}
            }
        )

    # reschedule
    if not exception_request.session_id:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "session_id required for reschedule"}
        )

    session_obj = await Session.get(
        exception_request.session_id,
        fetch_links=True
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
        Session.academic_year == session_obj.academic_year,
        Session.department == session_obj.department,
        Session.program == session_obj.program,
        Session.semester == session_obj.semester,
        fetch_links=True
    ).to_list()

    target_sessions = [
        s for s in overlapping_sessions
        if str(s.teacher.id) != str(requester.id)
    ]

    overlap_count = len(target_sessions)

    if overlap_count > 1:
        return overlap_error_response(overlap_count)

    if overlap_count == 1 and not confirm_swap:
        target = target_sessions[0]
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "code": "OVERLAP_FOUND",
                "message": "Reschedule overlaps with another session",
                "data": {
                    "can_swap": True,
                    "conflicting_teacher": f"{target.teacher.first_name} {target.teacher.last_name}",
                    "conflicting_session_id": str(target.id),
                    "time": f"{target.start_time}-{target.end_time}"
                }
            }
        )

    source_exception = ExceptionSession(
        session=session_obj,
        date=ex_date,
        action="Reschedule",
        reason=exception_request.reason,
        start_time=start_time,
        end_time=end_time,
        created_by=requester,
        swap_role="SOURCE"
    )
    await source_exception.insert()

    if overlap_count == 0:
        await notify_students_by_session(
            session=session_obj,
            title="Session Timing Updated",
            message=f"Session timing updated to {start_time}-{end_time}"
        )

        return JSONResponse(
            status_code=201,
            content={
                "success": True,
                "message": "Session rescheduled successfully",
                "data": {"exception_id": str(source_exception.id)}
            }
        )

    target = target_sessions[0]

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
            message="You have received a swap request",
            data={
                "route": f"/teacher/request/{str(source_exception.id)}",
                "type": "SWAP_REQUEST"
            }
        )
    )

    return JSONResponse(
        status_code=201,
        content={
            "success": True,
            "message": "Swap request sent for approval",
            "data": {"swap_id": str(swap.id)}
        }
    )


# ---------------- take swap action ----------------

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
            content={"success": False, "message": "Not authorized"}
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
                data={
                    
                    "route": f"/teacher/request/{str(swap.exception.id)}",
                    "type": "SWAP_REQUEST"

                }
            )
        )

        return JSONResponse(
            status_code=200,
            content={"success": True, "message": "Swap rejected"}
        )

    swap.status = "APPROVED"
    swap.responded_at = datetime.utcnow()
    await swap.save()

    source_exception = swap.exception
    source_session = swap.source_session
    target_session = swap.target_session

    source_original_start = source_session.start_time
    source_original_end = source_session.end_time
    target_original_start = target_session.start_time
    target_original_end = target_session.end_time

    source_exception.start_time = target_original_start
    source_exception.end_time = target_original_end
    await source_exception.save()

    target_exception = ExceptionSession(
        session=target_session,
        date=source_exception.date,
        action="Reschedule",
        reason="Swap approved",
        start_time=source_original_start,
        end_time=source_original_end,
        created_by=swap.requested_to,
        swap_id=swap,
        swap_role="TARGET"
    )
    await target_exception.insert()

    await notify_users(
        NotificationRequest(
            user="teacher",
            target_ids=[str(swap.requested_by.id)],
            title="Swap Approved",
            message="Your swap request has been approved",
            data={
                
                "route": f"/teacher/request/{str(source_exception.id)}",
                "type": "SWAP_REQUEST"
                
            }
        )
    )

    await notify_students_for_two_sessions(
        source_session,
        target_session,
        title="Session Timing Updated",
        message="Your session timing has been updated. Please check the app."
    )

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "Swap approved and applied correctly",
            "data": {"swap_id": str(swap.id)}
        }
    )
