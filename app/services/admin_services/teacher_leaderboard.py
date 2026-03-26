from datetime import datetime, timedelta, timezone
import json
from typing import Optional
from fastapi import Request
from fastapi.responses import JSONResponse
from app.schemas.attendance import Attendance
from app.core.redis import get_redis_client


async def get_teacher_leaderboard(
    request: Request,
    department: Optional[str] = None,
    program: Optional[str] = None,
    period: Optional[str] = "monthly",   #weekly | monthly | custom
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> JSONResponse:

    try:
        redis = await get_redis_client()

        #always use timezone aware datetime
        now = datetime.now(timezone.utc)

        #period logic
        if period == "weekly":
            start = now - timedelta(days=7)
            end = now
            # start = datetime(2025, 10, 11, tzinfo=timezone.utc)
            # end = datetime(2025, 10, 18, tzinfo=timezone.utc)

        elif period == "monthly":
            #start = now - timedelta(days=30)
            #end = now
            start = datetime(2025, 5, 31, tzinfo=timezone.utc)
            end = datetime(2025, 7, 31, tzinfo=timezone.utc)

        elif period == "custom":
            start = start_date or datetime(2000, 1, 1, tzinfo=timezone.utc)
            end = end_date or now

        else:
            start = now - timedelta(days=30)
            end = now

        #min sessions logic
        min_sessions = 0 if period == "weekly" else 10

        #cache key (important fix)
        cache_key = f"leaderboard:{department}:{program}:{period}:{start.isoformat()}:{end.isoformat()}"

        cached = await redis.get(cache_key)
        if cached:
            return JSONResponse(status_code=200, content=json.loads(cached))

        pipeline = [

            #join session
            {
                "$lookup": {
                    "from": "sessions",
                    "localField": "session.$id",
                    "foreignField": "_id",
                    "as": "s"
                }
            },
            {"$unwind": {"path": "$s", "preserveNullAndEmptyArrays": True}},

            #join exception
            {
                "$lookup": {
                    "from": "exception_sessions",
                    "localField": "exception_session.$id",
                    "foreignField": "_id",
                    "as": "e"
                }
            },
            {"$unwind": {"path": "$e", "preserveNullAndEmptyArrays": True}},

            #extract teacher + subject
            {
                "$addFields": {
                    "teacher_id": {
                        "$ifNull": ["$s.teacher.$id", "$e.teacher.$id"]
                    },
                    "subject_id": {
                        "$ifNull": ["$s.subject.$id", "$e.subject.$id"]
                    }
                }
            },

            #filter by date
            {
                "$match": {
                    "teacher_id": {"$ne": None},
                    "date": {"$gte": start, "$lte": end}
                }
            },

            #join teacher
            {
                "$lookup": {
                    "from": "teachers",
                    "localField": "teacher_id",
                    "foreignField": "_id",
                    "pipeline": [
                        {
                            "$project": {
                                "first_name": 1,
                                "last_name": 1,
                                "department": 1,
                                "profile_picture": 1
                            }
                        }
                    ],
                    "as": "t"
                }
            },
            {"$unwind": "$t"},

            *(
                [{"$match": {"t.department": department}}]
                if department else []
            ),

            #join subject
            {
                "$lookup": {
                    "from": "subjects",
                    "localField": "subject_id",
                    "foreignField": "_id",
                    "pipeline": [{"$project": {"program": 1}}],
                    "as": "sub"
                }
            },
            {"$unwind": {"path": "$sub", "preserveNullAndEmptyArrays": True}},

            *(
                [{"$match": {"sub.program": program}}]
                if program else []
            ),

            #calculate attendance
            {
                "$addFields": {
                    "total_students": {"$strLenCP": {"$ifNull": ["$students", ""]}},
                    "present_students": {
                        "$size": {
                            "$filter": {
                                "input": {
                                    "$map": {
                                        "input": {
                                            "$range": [
                                                0,
                                                {"$strLenCP": {"$ifNull": ["$students", ""]}}
                                            ]
                                        },
                                        "as": "i",
                                        "in": {"$substrCP": ["$students", "$$i", 1]}
                                    }
                                },
                                "as": "c",
                                "cond": {"$eq": ["$$c", "1"]}
                            }
                        }
                    }
                }
            },

            #group per teacher
            {
                "$group": {
                    "_id": "$teacher_id",

                    "first_name": {"$first": "$t.first_name"},
                    "last_name": {"$first": "$t.last_name"},
                    "department": {"$first": "$t.department"},
                    "profile_picture": {"$first": "$t.profile_picture"},

                    "sum_present": {"$sum": "$present_students"},
                    "sum_total": {"$sum": "$total_students"},

                    "conducted": {"$sum": 1},

                    "rescheduled": {
                        "$sum": {
                            "$cond": [{"$eq": ["$e.action", "Reschedule"]}, 1, 0]
                        }
                    }
                }
            },

            #lookup cancellations
            {
                "$lookup": {
                    "from": "exception_sessions",
                    "let": {"tid": "$_id"},
                    "pipeline": [
                        {
                            "$match": {
                                "$expr": {"$eq": ["$teacher.$id", "$$tid"]},
                                "action": "Cancel",
                                "date": {"$gte": start, "$lte": end}
                            }
                        },
                        {"$count": "count"}
                    ],
                    "as": "c"
                }
            },

            {
                "$addFields": {
                    "cancelled": {
                        "$ifNull": [{"$arrayElemAt": ["$c.count", 0]}, 0]
                    }
                }
            },

            #metrics
            {
                "$addFields": {
                    "total_sessions": {"$add": ["$conducted", "$cancelled"]},
                    "attendance_rate": {
                        "$cond": [
                            {"$gt": ["$sum_total", 0]},
                            {"$divide": ["$sum_present", "$sum_total"]},
                            0
                        ]
                    }
                }
            },

            #min sessions (dynamic)
            *(
                [{
                    "$match": {
                        "total_sessions": {"$gte": min_sessions}
                    }
                }]
                if min_sessions > 0 else []
            ),

            #rates
            {
                "$addFields": {
                    "cancellation_rate": {
                        "$divide": ["$cancelled", "$total_sessions"]
                    },
                    "reschedule_rate": {
                        "$divide": ["$rescheduled", "$total_sessions"]
                    }
                }
            },

            #score
            {
                "$addFields": {
                    "raw_score": {
                        "$add": [
                            {"$multiply": ["$attendance_rate", 60]},
                            {"$multiply": [{"$subtract": [1, "$cancellation_rate"]}, 10]},
                            {"$multiply": [{"$subtract": [1, "$reschedule_rate"]}, 5]}
                        ]
                    }
                }
            },

            #normalize
            {
                "$addFields": {
                    "score": {
                        "$multiply": [
                            {"$divide": ["$raw_score", 75]},
                            100
                        ]
                    }
                }
            },

            #sort + limit
            {"$sort": {"score": -1}},
            {"$limit": 4},

            #final output
            {
                "$project": {
                    "_id": 0,
                    "teacher_id": {"$toString": "$_id"},
                    "name": {"$concat": ["$first_name", " ", "$last_name"]},
                    "department": 1,
                    "profile_picture": 1,
                    "score": {"$round": ["$score", 1]},
                    "attendance_rate": {
                        "$round": [
                            {"$multiply": ["$attendance_rate", 100]},
                            1
                        ]
                    }
                }
            }
        ]

        data = await Attendance.aggregate(pipeline).to_list()

        #rank + badge
        for i, t in enumerate(data):
            t["rank"] = i + 1
            t["badge"] = ["Gold", "Silver", "Bronze"][i] if i < 3 else None

        result = {
            "success": True,
            "period": period,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "data": data
        }

        await redis.set(cache_key, json.dumps(result), ex=300)

        return JSONResponse(status_code=200, content=result)

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )