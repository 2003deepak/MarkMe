from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Request
from fastapi.responses import JSONResponse
from app.schemas.subject_session_stats import SubjectSessionStats


async def get_extremes(
    request: Request,
    department: Optional[str] = None,
    program: Optional[str] = None,
    period: Optional[str] = "weekly"
):

    try:

        #period logic
        now = datetime.now(timezone.utc)
    
        if period == "weekly":
            # Last 7 days including today
            start = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
            end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        else:
            # Current month: From the 1st day of the current month to now
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            # End of the month (current moment or end of day)
            end = now.replace(hour=23, minute=59, second=59, microsecond=999999)

        base_pipeline = [

            #filter by date
            {
                "$match": {
                    "date": {"$gte": start, "$lte": end}
                }
            },

            #join subject
            {
                "$lookup": {
                    "from": "subjects",
                    "localField": "subject.$id",
                    "foreignField": "_id",
                    "pipeline": [
                        {
                            "$project": {
                                "subject_name": 1,
                                "program": 1
                            }
                        }
                    ],
                    "as": "sub"
                }
            },
            {"$unwind": "$sub"},

            #program filter
            *(
                [{"$match": {"sub.program": program}}]
                if program else []
            ),

            #join attendance
            {
                "$lookup": {
                    "from": "attendances",
                    "localField": "session_id.$id",
                    "foreignField": "_id",
                    "as": "att"
                }
            },
            {"$unwind": "$att"},

            #join session
            {
                "$lookup": {
                    "from": "sessions",
                    "localField": "att.session.$id",
                    "foreignField": "_id",
                    "pipeline": [
                        {
                            "$project": {
                                "start_time": 1,
                                "end_time": 1,
                                "department": 1
                            }
                        }
                    ],
                    "as": "s"
                }
            },
            {"$unwind": {"path": "$s", "preserveNullAndEmptyArrays": True}},

            #join exception_session
            {
                "$lookup": {
                    "from": "exception_sessions",
                    "localField": "att.exception_session.$id",
                    "foreignField": "_id",
                    "pipeline": [
                        {
                            "$project": {
                                "start_time": 1,
                                "end_time": 1,
                                "department": 1
                            }
                        }
                    ],
                    "as": "e"
                }
            },
            {"$unwind": {"path": "$e", "preserveNullAndEmptyArrays": True}},

            #department filter
            *(
                [{
                    "$match": {
                        "$or": [
                            {"s.department": department},
                            {"e.department": department}
                        ]
                    }
                }]
                if department else []
            ),

            #merge times
            {
                "$addFields": {
                    "start_time": {
                        "$ifNull": ["$s.start_time", "$e.start_time"]
                    },
                    "end_time": {
                        "$ifNull": ["$s.end_time", "$e.end_time"]
                    }
                }
            },

            #final output
            {
                "$project": {
                    "_id": 0,
                    "date": {
                        "$dateToString": {
                            "format": "%d %b",
                            "date": "$date"
                        }
                    },
                    "subject": "$sub.subject_name",
                    "attendance": {
                        "$round": ["$percentage_present", 1]
                    },
                    
                }
            }
        ]

        #highest attendance
        highest = await SubjectSessionStats.aggregate(
            base_pipeline + [
                {"$sort": {"attendance": -1}},
                {"$limit": 1}
            ]
        ).to_list()

        #lowest attendance
        lowest = await SubjectSessionStats.aggregate(
            base_pipeline + [
                {"$sort": {"attendance": 1}},
                {"$limit": 1}
            ]
        ).to_list()

        result = {
            "success": True,
            "period": period,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "weekly_extremes": {
                "highest": highest[0] if highest else None,
                "lowest": lowest[0] if lowest else None
            }
        }

        return JSONResponse(status_code=200, content=result)

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )