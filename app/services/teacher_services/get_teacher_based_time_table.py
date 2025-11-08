# app/services/teacher_services/get_teacher_based_time_table.py
from typing import Dict, List
from fastapi import Request
from fastapi.responses import JSONResponse
from app.models.allModel import SessionView
from app.schemas.session import Session
from app.core.redis import redis_client
from beanie.operators import Eq
from bson import DBRef, ObjectId
import json

async def get_teacher_based_time_table(request: Request) -> JSONResponse:
    user_role = request.state.user.get("role")
    user_id   = request.state.user.get("id")

    if user_role != "teacher":
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "User must be a teacher only"}
        )

    cache_key = f"timetable:teacher:{user_id}"
    cached = await redis_client.get(cache_key)
    if cached:
        return JSONResponse(status_code=200, content=json.loads(cached))

    # 1. Fetch sessions
    sessions = await Session.find_many(
        Eq(Session.teacher.id, ObjectId(user_id)),
        fetch_links=True
    ).to_list()

    if not sessions:
        empty = {
            "success": True,
            "message": "No timetable found for this teacher",
            "data": {}
        }
        await redis_client.setex(cache_key, 3600, json.dumps(empty))
        return JSONResponse(status_code=200, content=empty)

    # 2. Fetch linked subject & teacher
    for s in sessions:
        if s.subject and isinstance(s.subject, DBRef):
            s.subject = await s.subject.fetch()
        if s.teacher and isinstance(s.teacher, DBRef):
            s.teacher = await s.teacher.fetch()

    # 3. Group by day → list of sessions
    days_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    schedule_by_day: Dict[str, List[SessionView]] = {day: [] for day in days_order}

    for s in sessions:
        view = SessionView(
            program=s.program,
            semester=s.semester,
            subject_name=s.subject.subject_name if s.subject else "N/A",
            start_time=s.start_time,
            end_time=s.end_time,
            component=s.subject.component if s.subject else "N/A"
        )
        schedule_by_day[s.day].append(view)

    # 4. Sort sessions inside each day by start_time
    for day in schedule_by_day:
        schedule_by_day[day].sort(key=lambda x: x.start_time)

    # 5. Build final payload (only include days with sessions)
    data_payload = {day: [sess.dict() for sess in sessions] for day, sessions in schedule_by_day.items() if sessions}

    payload = {
        "success": True,
        "message": "Time Table Records fetched successfully",
        "data": data_payload
    }

    await redis_client.setex(cache_key, 3600, json.dumps(payload))
    return JSONResponse(status_code=200, content=payload)