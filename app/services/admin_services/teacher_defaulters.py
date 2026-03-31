from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from bson import ObjectId
from datetime import datetime

from app.schemas.session import Session


async def teacher_defaulters(
    request: Request,
    page: int = 1,
    limit: int = 10,
    department: str | None = None,
    program: str | None = None,
    semester: str | None = None
):

    #auth
    user_role = request.state.user.get("role")

    if user_role != "admin":
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "message": "Only Admin can access this route"
            }
        )

    skip = (page - 1) * limit

    match_stage = {}

    if department:
        match_stage["department"] = department

    if program:
        match_stage["program"] = program

    if semester:
        match_stage["semester"] = semester

    pipeline = []

    if match_stage:
        pipeline.append({"$match": match_stage})

    pipeline.extend([
        {
            "$lookup": {
                "from": "exception_sessions",
                "localField": "_id",
                "foreignField": "session.$id",
                "as": "exceptions"
            }
        },
        {
            "$lookup": {
                "from": "attendances",
                "localField": "_id",
                "foreignField": "session.$id",
                "as": "attendance"
            }
        },
        {
            "$lookup": {
                "from": "subject_session_stats",
                "localField": "_id",
                "foreignField": "session_id.$id",
                "as": "stats"
            }
        },
        {
            "$group": {
                "_id": "$teacher.$id",

                "total_sessions": {"$sum": 1},

                "cancelled_sessions": {
                    "$sum": {
                        "$size": {
                            "$filter": {
                                "input": "$exceptions",
                                "as": "ex",
                                "cond": {"$eq": ["$$ex.action", "Cancel"]}
                            }
                        }
                    }
                },

                "total_exceptions": {
                    "$sum": {"$size": "$exceptions"}
                },

                "swap_sessions": {
                    "$sum": {
                        "$size": {
                            "$filter": {
                                "input": "$exceptions",
                                "as": "ex",
                                "cond": {"$ne": ["$$ex.swap_id", None]}
                            }
                        }
                    }
                },

                "low_attendance_sessions": {
                    "$sum": {
                        "$size": {
                            "$filter": {
                                "input": "$stats",
                                "as": "st",
                                "cond": {"$lt": ["$$st.percentage_present", 40]}
                            }
                        }
                    }
                },

                "total_stats": {"$sum": {"$size": "$stats"}}
            }
        },

        {
            "$addFields": {

                "cancellation_rate": {
                    "$cond": [
                        {"$eq": ["$total_sessions", 0]},
                        0,
                        {"$divide": ["$cancelled_sessions", "$total_sessions"]}
                    ]
                },

                "exception_rate": {
                    "$cond": [
                        {"$eq": ["$total_sessions", 0]},
                        0,
                        {"$divide": ["$total_exceptions", "$total_sessions"]}
                    ]
                },

                "swap_rate": {
                    "$cond": [
                        {"$eq": ["$total_sessions", 0]},
                        0,
                        {"$divide": ["$swap_sessions", "$total_sessions"]}
                    ]
                },

                "low_attendance_rate": {
                    "$cond": [
                        {"$eq": ["$total_stats", 0]},
                        0,
                        {"$divide": ["$low_attendance_sessions", "$total_stats"]}
                    ]
                }
            }
        },

        {
            "$addFields": {

                "score": {
                    "$add": [
                        {"$multiply": [0.30, "$cancellation_rate"]},
                        {"$multiply": [0.20, "$exception_rate"]},
                        {"$multiply": [0.25, "$low_attendance_rate"]},
                        {"$multiply": [0.10, "$swap_rate"]}
                    ]
                }
            }
        },
        
        {
            "$match": {
                "score": {"$gt": 0.20}
            }
        },

        {
            "$lookup": {
                "from": "teachers",
                "localField": "_id",
                "foreignField": "_id",
                "as": "teacher"
            }
        },

        {"$unwind": "$teacher"},

        {
            "$addFields": {
                "status": {
                    "$switch": {
                        "branches": [
                            {"case": {"$gt": ["$score", 0.40]}, "then": "DEFAULTER"},
                            {"case": {"$gt": ["$score", 0.20]}, "then": "MONITOR"}
                        ],
                        "default": "GOOD"
                    }
                }
            }
        },

        {
            "$project": {
                "_id": 0,
                "teacher_id": "$teacher.teacher_id",
                "name": {
                    "$concat": ["$teacher.first_name", " ", "$teacher.last_name"]
                },
                "department": "$teacher.department",
                "total_sessions": 1,
                "cancellation_rate": {"$round": ["$cancellation_rate", 2]},
                "exception_rate": {"$round": ["$exception_rate", 2]},
                "low_attendance_rate": {"$round": ["$low_attendance_rate", 2]},
                "swap_rate": {"$round": ["$swap_rate", 2]},
                "score": {"$round": ["$score", 3]}
            }
        },

        {"$sort": {"score": -1}},
        {"$skip": skip},
        {"$limit": limit}
    ])

    result = await Session.aggregate(pipeline).to_list()

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "Teacher defaulters fetched successfully",
            "data": jsonable_encoder(
                result,
                custom_encoder={ObjectId: str, datetime: lambda x: x.isoformat()}
            )
        }
    )