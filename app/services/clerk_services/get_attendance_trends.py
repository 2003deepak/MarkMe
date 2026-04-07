from datetime import datetime, timedelta
from typing import Literal
from bson import ObjectId
from fastapi import Request
from fastapi.responses import JSONResponse
from zoneinfo import ZoneInfo
import hashlib
import json

from app.schemas.subject_session_stats import SubjectSessionStats
from app.core.redis import get_redis_client

IST = ZoneInfo("Asia/Kolkata")


async def get_attendance_trends(
    request: Request,
    time_range: Literal["week", "month"] = "week",
    teacher_id: str = None,
    program: str = None,
    department: str = None,
    semester: int = None,
    subject_id: str = None,
):

    # auth
    if request.state.user.get("role") not in ["clerk", "admin"]:
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Access denied"}
        )
        
    redis = await get_redis_client()

    # =========================
    # cache key
    # =========================
    cache_payload = {
        "range": time_range,
        "teacher_id": teacher_id,
        "program": program,
        "department": department,
        "semester": semester,
        "subject_id": subject_id,
    }

    cache_key = f"analytics:attendance_trends:{hashlib.md5(json.dumps(cache_payload, sort_keys=True).encode()).hexdigest()}"

    cached = await redis.get(cache_key)
    if cached:
        return JSONResponse(status_code=200, content=json.loads(cached))

    # =========================
    # date range
    # =========================
    today = datetime.now(IST).date()

    if time_range == "week":
        start_date = today - timedelta(days=today.weekday())
        end_date = start_date + timedelta(days=6)

    elif time_range == "month":
        start_date = today.replace(day=1)

        if today.month == 12:
            next_month = today.replace(year=today.year + 1, month=1, day=1)
        else:
            next_month = today.replace(month=today.month + 1, day=1)

        end_date = next_month - timedelta(days=1)

    else:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Invalid range"}
        )

    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date, datetime.max.time())

    match_stage = {
        "date": {"$gte": start_dt, "$lte": end_dt}
    }

    if subject_id:
        match_stage["subject.$id"] = ObjectId(subject_id)

    # =========================
    # dynamic grouping
    # =========================
    if time_range == "week":
        add_fields_stage = {
            "$addFields": {
                "group_key": {
                    "$dayOfWeek": {
                        "date": "$date",
                        "timezone": "Asia/Kolkata"
                    }
                }
            }
        }

    elif time_range == "month":
        add_fields_stage = {
            "$addFields": {
                "group_key": {
                    "$ceil": {
                        "$divide": [
                            {"$dayOfMonth": {
                                "date": "$date",
                                "timezone": "Asia/Kolkata"
                            }},
                            7
                        ]
                    }
                }
            }
        }

    pipeline = [
        {"$match": match_stage},

        {
            "$lookup": {
                "from": "subjects",
                "localField": "subject.$id",
                "foreignField": "_id",
                "as": "subject"
            }
        },
        {"$unwind": "$subject"},

        {
            "$match": {
                **({"subject.program": program} if program else {}),
                **({"subject.department": department} if department else {}),
                **({"subject.semester": semester} if semester else {}),
                **({
                    "subject.teacher_assigned.$id": ObjectId(teacher_id)
                } if teacher_id else {})
            }
        },

        add_fields_stage,

        {
            "$group": {
                "_id": "$group_key",
                "avg_attendance": {"$avg": "$percentage_present"}
            }
        },

        {
            "$project": {
                "_id": 0,
                "group_key": "$_id",
                "attendance": {"$round": ["$avg_attendance", 2]}
            }
        }
    ]

    results = await SubjectSessionStats.aggregate(pipeline).to_list()

    # =========================
    # formatting
    # =========================
    if time_range == "week":
        day_map = {
            1: "SUN", 2: "MON", 3: "TUE",
            4: "WED", 5: "THU", 6: "FRI", 7: "SAT"
        }

        data_map = {
            day_map[item["group_key"]]: item["attendance"]
            for item in results
        }

        order = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]

        final_data = [
            {"label": day, "attendance": data_map.get(day, 0)}
            for day in order
        ]

    else:  # month
        data_map = {
            item["group_key"]: item["attendance"]
            for item in results
        }

        final_data = [
            {"label": f"Week {i}", "attendance": data_map.get(i, 0)}
            for i in range(1, 6)
        ]

    response = {
        "success": True,
        "message": "Attendance trends fetched successfully",
        "data": final_data
    }

    # cache (5 min)
    await redis.set(cache_key, json.dumps(response), ex=300)

    return JSONResponse(status_code=200, content=response)