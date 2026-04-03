from bson import ObjectId
from fastapi import Request
from fastapi.responses import JSONResponse
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from app.schemas.session import Session
from app.schemas.attendance import Attendance
from app.schemas.exception_session import ExceptionSession
from app.schemas.subject import Subject

IST = ZoneInfo("Asia/Kolkata")


async def get_teacher_session_compliance(
    request: Request,
    teacher_id: str,
):
    # auth
    if request.state.user.get("role") != "clerk":
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Access denied"}
        )

    try:
        teacher_oid = ObjectId(teacher_id)
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Invalid teacher id"}
        )

    # 1️⃣ scheduled sessions (teacher-wise + subject-wise)
    scheduled_pipeline = [
        {"$match": {"teacher.$id": teacher_oid, "is_active": True}},
        {
            "$group": {
                "_id": "$subject.$id",
                "scheduled_sessions": {"$sum": 1}
            }
        }
    ]

    scheduled = await Session.aggregate(
        scheduled_pipeline
    ).to_list(length=None)

    if not scheduled:
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "No sessions found for this teacher",
                "data": {}
            }
        )

    subject_map = {
        str(item["_id"]): {
            "subject_id": str(item["_id"]),
            "scheduled_sessions": item["scheduled_sessions"],
            "attendance_marked": 0,
            "cancelled_sessions": 0,
            "rescheduled_sessions": 0
        }
        for item in scheduled
    }

    subject_ids = [ObjectId(sid) for sid in subject_map.keys()]

    # 2️⃣ attendance marked
    attendance_pipeline = [
        {"$match": {"session": {"$ne": None}}},
        {
            "$lookup": {
                "from": "sessions",
                "localField": "session",
                "foreignField": "_id",
                "as": "session"
            }
        },
        {"$unwind": "$session"},
        {"$match": {"session.teacher.$id": teacher_oid}},
        {
            "$group": {
                "_id": "$session.subject.$id",
                "count": {"$addToSet": "$session._id"}
            }
        },
        {
            "$project": {
                "attendance_marked": {"$size": "$count"}
            }
        }
    ]

    attendance = await Attendance.aggregate(
        attendance_pipeline
    ).to_list(length=None)

    for item in attendance:
        sid = str(item["_id"])
        if sid in subject_map:
            subject_map[sid]["attendance_marked"] = item["attendance_marked"]

    # 3️⃣ exception sessions
    exception_pipeline = [
        {"$match": {"teacher.$id": teacher_oid}},
        {
            "$group": {
                "_id": {
                    "subject": "$subject.$id",
                    "action": "$action"
                },
                "count": {"$sum": 1}
            }
        }
    ]

    exceptions = await ExceptionSession.aggregate(
        exception_pipeline
    ).to_list(length=None)

    for item in exceptions:
        sid = str(item["_id"]["subject"])
        action = item["_id"]["action"]

        if sid not in subject_map:
            continue

        if action == "Cancel":
            subject_map[sid]["cancelled_sessions"] += item["count"]
        elif action == "Reschedule":
            subject_map[sid]["rescheduled_sessions"] += item["count"]

    # 4️⃣ enrich with subject details + calculations
    subject_docs = await Subject.find(
        {"_id": {"$in": subject_ids}}
    ).to_list()

    subject_name_map = {
        str(s.id): {
            "subject_name": s.subject_name,
            "component": s.component
        }
        for s in subject_docs
    }

    subjects_response = []
    total_scheduled = 0
    total_conducted = 0
    total_missed = 0

    for sid, data in subject_map.items():
        scheduled_sessions = data["scheduled_sessions"]
        conducted = data["attendance_marked"]
        cancelled = data["cancelled_sessions"]
        rescheduled = data["rescheduled_sessions"]

        missed = max(
            scheduled_sessions - conducted - cancelled,
            0
        )

        compliance = (
            round((conducted / scheduled_sessions) * 100, 2)
            if scheduled_sessions > 0 else 0
        )

        total_scheduled += scheduled_sessions
        total_conducted += conducted
        total_missed += missed

        subjects_response.append({
            "subject_id": sid,
            "subject_name": subject_name_map.get(sid, {}).get("subject_name"),
            "component": subject_name_map.get(sid, {}).get("component"),
            "scheduled_sessions": scheduled_sessions,
            "sessions_conducted": conducted,
            "missed_sessions": missed,
            "cancelled_sessions": cancelled,
            "rescheduled_sessions": rescheduled,
            "compliance_percentage": compliance,
            "status": (
                "OK" if compliance >= 95
                else "WARNING" if compliance >= 90
                else "CRITICAL"
            )
        })

    overall_compliance = (
        round((total_conducted / total_scheduled) * 100, 2)
        if total_scheduled > 0 else 0
    )

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "teacher_id": teacher_id,
            "overall": {
                "scheduled_sessions": total_scheduled,
                "sessions_conducted": total_conducted,
                "missed_sessions": total_missed,
                "compliance_percentage": overall_compliance,
                "status": (
                    "OK" if overall_compliance >= 95
                    else "WARNING" if overall_compliance >= 90
                    else "CRITICAL"
                )
            },
            "subjects": subjects_response
        }
    )
