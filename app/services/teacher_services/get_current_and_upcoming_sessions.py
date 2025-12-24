from bson import ObjectId
from fastapi import Request
from fastapi.responses import JSONResponse
from datetime import datetime
from zoneinfo import ZoneInfo
import logging

from beanie.operators import Or
from app.schemas.session import Session
from app.schemas.attendance import Attendance
from app.schemas.exception_session import ExceptionSession
from app.schemas.swap_approval import SwapApproval
from app.utils.parse_data import _build_swap_payload

logger = logging.getLogger("session_exception")
IST = ZoneInfo("Asia/Kolkata")


async def get_current_and_upcoming_sessions(request: Request):
    logger.info("===== FETCH CURRENT & UPCOMING SESSIONS START =====")

    # auth
    user = request.state.user
    if user.get("role") != "teacher":
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Only teachers can access"}
        )

    teacher_id = ObjectId(user["id"])

    # date context
    now = datetime.now(tz=IST)
    today = now.date()
    weekday = now.strftime("%A")

    day_start = datetime.combine(today, datetime.min.time()).replace(tzinfo=IST)
    day_end = datetime.combine(today, datetime.max.time()).replace(tzinfo=IST)

    # 1️⃣ base sessions
    base_sessions = await Session.find(
        Session.day == weekday,
        Session.teacher.id == teacher_id,
        fetch_links=True
    ).to_list()

    base_session_map = {str(s.id): s for s in base_sessions}

    # 2️⃣ exceptions
    exceptions = await ExceptionSession.find(
        ExceptionSession.date >= day_start,
        ExceptionSession.date <= day_end,
        Or(
            ExceptionSession.created_by.id == teacher_id,
            ExceptionSession.swap_id.requested_to.id == teacher_id
        ),
        fetch_links=True
    ).to_list()

    cancel_map = {}
    reschedule_map = {}
    target_swap_sessions = {}

    # 3️⃣ process exceptions
    for ex in exceptions:
        # swap must be approved
        if ex.swap_id and ex.swap_id.status != "APPROVED":
            continue

        sid = str(ex.session.id)

        if ex.action == "Cancel":
            cancel_map[sid] = ex

        elif ex.action == "Reschedule":
            # SOURCE and TARGET both mean RESCHEDULE now
            reschedule_map[sid] = ex

            if ex.swap_role == "TARGET":
                target_swap_sessions[sid] = ex

    final_sessions = []
    added_session_ids = set()

    # 4️⃣ apply to base sessions
    for sid, session in base_session_map.items():

        if sid in cancel_map:
            continue

        if sid in reschedule_map:
            ex = reschedule_map[sid]
            session.start_time = ex.start_time
            session.end_time = ex.end_time

        final_sessions.append(session)
        added_session_ids.add(sid)

    # 5️⃣ inject TARGET swap sessions if missing
    for sid, ex in target_swap_sessions.items():
        if sid not in added_session_ids:
            injected = ex.session
            injected.start_time = ex.start_time
            injected.end_time = ex.end_time
            final_sessions.append(injected)
            added_session_ids.add(sid)

    # 6️⃣ attendance
    attendance_list = await Attendance.find(
        Attendance.date >= day_start,
        Attendance.date <= day_end,
        fetch_links=True
    ).to_list()

    attendance_map = {
        str(a.session.id): a
        for a in attendance_list
        if a.session
    }

    upcoming = []
    current = []
    past = []

    # 7️⃣ classify
    for s in final_sessions:
        start_dt = datetime.strptime(
            f"{today} {s.start_time}", "%Y-%m-%d %H:%M"
        ).replace(tzinfo=IST)

        end_dt = datetime.strptime(
            f"{today} {s.end_time}", "%Y-%m-%d %H:%M"
        ).replace(tzinfo=IST)

        attendance = attendance_map.get(str(s.id))
        attendance_id = str(attendance.id) if attendance else None

        payload = {
            "session_id": str(s.id),
            "attendance_id": attendance_id,
            "date": today.strftime("%Y-%m-%d"),
            "start_time": s.start_time,
            "end_time": s.end_time,
            "subject_name": s.subject.subject_name,
            "subject_code": s.subject.subject_code,
            "component": s.subject.component,
            "program": s.program,
            "department": s.department,
            "semester": s.semester,
            "academic_year": s.academic_year,
            "teacher_name": f"{s.teacher.first_name} {s.teacher.last_name}"
        }

        if start_dt <= now <= end_dt:
            current.append(payload)
        elif start_dt > now:
            upcoming.append(payload)
        else:
            past.append(payload)

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "Sessions fetched successfully",
            "data": {
                "upcoming": upcoming,
                "current": current,
                "past": past
            }
        }
    )


async def fetch_teacher_request(request: Request):
    logger.info("===== FETCH TEACHER REQUESTS (LIST) START =====")

    user = request.state.user
    if user.get("role") != "teacher":
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Only teachers can access"}
        )

    teacher_id = ObjectId(user["id"])
    logger.info(f"Teacher ID → {teacher_id}")

    # --------------------------------------------------
    # 1️⃣ CREATED BY ME
    # --------------------------------------------------
    created_pipeline = [
        {"$match": {"created_by.$id": teacher_id}},
        {
            "$lookup": {
                "from": "sessions",
                "localField": "session.$id",
                "foreignField": "_id",
                "as": "session_doc"
            }
        },
        {"$unwind": {"path": "$session_doc", "preserveNullAndEmptyArrays": True}},
        {
            "$lookup": {
                "from": "subjects",
                "localField": "session_doc.subject.$id",
                "foreignField": "_id",
                "as": "subject_doc"
            }
        },
        {"$unwind": {"path": "$subject_doc", "preserveNullAndEmptyArrays": True}},
        {
            "$lookup": {
                "from": "swap_approvals",
                "localField": "swap_id.$id",
                "foreignField": "_id",
                "as": "swap"
            }
        },
        {"$unwind": {"path": "$swap", "preserveNullAndEmptyArrays": True}},
        {"$sort": {"created_at": -1}}
    ]


    created = await ExceptionSession.aggregate(created_pipeline).to_list(None)
    logger.info(f"Created by me → {len(created)}")

    # --------------------------------------------------
    # 2️⃣ REQUESTED TO ME
    # --------------------------------------------------
    received_pipeline = [
    {"$match": {"requested_to.$id": teacher_id}},
    {
        "$lookup": {
            "from": "exception_sessions",
            "localField": "exception.$id",
            "foreignField": "_id",
            "as": "exception"
        }
    },
    {"$unwind": "$exception"},
    {
        "$lookup": {
            "from": "sessions",
            "localField": "exception.session.$id",
            "foreignField": "_id",
            "as": "session_doc"
        }
    },
    {"$unwind": {"path": "$session_doc", "preserveNullAndEmptyArrays": True}},
    {
        "$lookup": {
            "from": "subjects",
            "localField": "session_doc.subject.$id",
            "foreignField": "_id",
            "as": "subject_doc"
        }
    },
    {"$unwind": {"path": "$subject_doc", "preserveNullAndEmptyArrays": True}},
    {"$sort": {"created_at": -1}}
]


    received = await SwapApproval.aggregate(received_pipeline).to_list(None)
    logger.info(f"Received by me → {len(received)}")

    # --------------------------------------------------
    # 3️⃣ NORMALIZE
    # --------------------------------------------------
    result = []
    seen = set()

    # Created by me
    for doc in created:
        exc_id = str(doc["_id"])
        seen.add(exc_id)

        swap = doc.get("swap")
        status = swap["status"] if swap else "APPROVED"

        request_type = (
            "Swap"
            if doc["action"] == "Reschedule" and swap
            else doc["action"]
        )

        result.append({
            "request_id": exc_id,
            "request_type": request_type,
            "status": status,
            "subject_name": doc["subject_doc"]["subject_name"] if doc.get("subject_doc") else None,
            "date_raised": doc["created_at"].isoformat(),
            "created_by_me": True,
            "received_by_me": False,
            "can_take_action": False
        })

    # Received by me
    for doc in received:
        exc = doc["exception"]
        exc_id = str(exc["_id"])

        if exc_id in seen:
            continue

        result.append({
            "request_id": exc_id,
            "request_type": "Swap",
            "status": doc["status"],
            "subject_name": doc["subject_doc"]["subject_name"] if doc.get("subject_doc") else None,
            "date_raised": exc["created_at"].isoformat(),
            "created_by_me": False,
            "received_by_me": True,
            "can_take_action": doc["status"] == "PENDING"
        })

    logger.info(f"FINAL LIST COUNT → {len(result)}")

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "data": result
        }
    )

async def fetch_detailed_teacher_request(
    request: Request,
    request_id: str
):
    logger.info("===== FETCH DETAILED TEACHER REQUEST START =====")

    user = request.state.user
    if user.get("role") != "teacher":
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Only teachers can access"}
        )

    teacher_id = ObjectId(user["id"])
    exception_id = ObjectId(request_id)

    # --------------------------------------------------
    # AGGREGATION PIPELINE
    # --------------------------------------------------
    pipeline = [
        {"$match": {"_id": exception_id}},

        # swap
        {
            "$lookup": {
                "from": "swap_approvals",
                "localField": "swap_id.$id",
                "foreignField": "_id",
                "as": "swap"
            }
        },
        {"$unwind": {"path": "$swap", "preserveNullAndEmptyArrays": True}},

        # requested_by teacher
        {
            "$lookup": {
                "from": "teachers",
                "localField": "swap.requested_by.$id",
                "foreignField": "_id",
                "as": "requested_by_teacher"
            }
        },
        {"$unwind": {"path": "$requested_by_teacher", "preserveNullAndEmptyArrays": True}},

        # approver (requested_to)
        {
            "$lookup": {
                "from": "teachers",
                "localField": "swap.requested_to.$id",
                "foreignField": "_id",
                "as": "approved_by_teacher"
            }
        },
        {"$unwind": {"path": "$approved_by_teacher", "preserveNullAndEmptyArrays": True}},

        # session
        {
            "$lookup": {
                "from": "sessions",
                "localField": "session.$id",
                "foreignField": "_id",
                "as": "session_doc"
            }
        },
        {"$unwind": {"path": "$session_doc", "preserveNullAndEmptyArrays": True}},

        # subject
        {
            "$lookup": {
                "from": "subjects",
                "localField": "session_doc.subject.$id",
                "foreignField": "_id",
                "as": "subject_doc"
            }
        },
        {"$unwind": {"path": "$subject_doc", "preserveNullAndEmptyArrays": True}},

        # creator
        {
            "$lookup": {
                "from": "teachers",
                "localField": "created_by.$id",
                "foreignField": "_id",
                "as": "created_by_teacher"
            }
        },
        {"$unwind": "$created_by_teacher"},
    ]

    docs = await ExceptionSession.aggregate(pipeline).to_list(1)

    if not docs:
        return JSONResponse(
            status_code=404,
            content={"success": False, "message": "Request not found"}
        )

    doc = docs[0]
    swap = doc.get("swap")

    # --------------------------------------------------
    # DERIVED LOGIC
    # --------------------------------------------------
    status = swap["status"] if swap else "APPROVED"

    request_type = (
        "Swap"
        if doc["action"] == "Reschedule" and swap
        else doc["action"]
    )

    can_take_action = (
        swap
        and swap["status"] == "PENDING"
        and doc["approved_by_teacher"]["_id"] == teacher_id
    )

    # --------------------------------------------------
    # RESPONSE
    # --------------------------------------------------
    response = {
        "request_id": str(doc["_id"]),
        "request_type": request_type,
        "status": status,
        "reason": doc.get("reason"),
        "date": doc["date"].isoformat(),
        "start_time": doc.get("start_time"),
        "end_time": doc.get("end_time"),
        "created_at": doc["created_at"].isoformat(),
        "created_by": {
            "teacher_id": str(doc["created_by_teacher"]["_id"]),
            "name": f"{doc['created_by_teacher']['first_name']} {doc['created_by_teacher']['last_name']}"
        },
        "subject": {
            "subject_id": str(doc["subject_doc"]["_id"]) if doc.get("subject_doc") else None,
            "subject_name": doc["subject_doc"]["subject_name"] if doc.get("subject_doc") else None,
            "subject_code": doc["subject_doc"]["subject_code"] if doc.get("subject_doc") else None,
            "component": doc["subject_doc"]["component"] if doc.get("subject_doc") else None
        },
        "swap": None,
        "can_take_action": can_take_action
    }

    if swap:
        response["swap"] = {
            "swap_id": str(swap["_id"]),
            "status": swap["status"],
            "requested_by": {
                "teacher_id": str(doc["requested_by_teacher"]["_id"]),
                "name": f"{doc['requested_by_teacher']['first_name']} {doc['requested_by_teacher']['last_name']}"
            },
            "approved_by": (
                {
                    "teacher_id": str(doc["approved_by_teacher"]["_id"]),
                    "name": f"{doc['approved_by_teacher']['first_name']} {doc['approved_by_teacher']['last_name']}"
                }
                if swap["status"] != "PENDING"
                else None
            ),
            "responded_at": (
                swap["responded_at"].isoformat()
                if swap.get("responded_at") else None
            )
        }

    logger.info("===== FETCH DETAILED TEACHER REQUEST END =====")

    return JSONResponse(
        status_code=200,
        content={"success": True, "data": response}
    )
