from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import Request
from fastapi.responses import JSONResponse

from app.schemas.attendance import Attendance

IST = ZoneInfo("Asia/Kolkata")


async def get_live_classes(request: Request) -> JSONResponse:



    if request.state.user.get("role") != "admin":
        
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "message": "You don't have right to create clerk"
            }
        )


    try:
        now = datetime.now(tz=IST)
        # current_time_str = now.strftime("%H:%M")
        current_time_str = "23:10"

        #date should match stored UTC midnight
        # today_date = datetime.combine(now.date(), datetime.min.time())
        today_date = datetime(2025, 6, 11, 0, 0, 0)

        pipeline = [
            #match today's attendance
            {
                "$match": {
                    "date": today_date
                }
            },

            #lookup session
            {
                "$lookup": {
                    "from": "sessions",
                    "localField": "session.$id",
                    "foreignField": "_id",
                    "as": "session_data"
                }
            },

            #lookup exception session
            {
                "$lookup": {
                    "from": "exception_sessions",
                    "localField": "exception_session.$id",
                    "foreignField": "_id",
                    "as": "exception_session_data"
                }
            },

            #unwind
            {
                "$unwind": {
                    "path": "$session_data",
                    "preserveNullAndEmptyArrays": True
                }
            },
            {
                "$unwind": {
                    "path": "$exception_session_data",
                    "preserveNullAndEmptyArrays": True
                }
            },

            #choose active session
            {
                "$addFields": {
                    "active_session": {
                        "$cond": {
                            "if": {"$ifNull": ["$exception_session_data._id", False]},
                            "then": "$exception_session_data",
                            "else": "$session_data"
                        }
                    }
                }
            },

            #filter live sessions
            {
                "$match": {
                    "$expr": {
                        "$and": [
                            {"$lte": ["$active_session.start_time", current_time_str]},
                            {"$gt": ["$active_session.end_time", current_time_str]}
                        ]
                    }
                }
            },

            #calculate attendance
            {
                "$addFields": {
                    "present_students": {
                        "$size": {
                            "$filter": {
                                "input": {
                                    "$map": {
                                        "input": {"$range": [0, {"$strLenCP": "$students"}]},
                                        "as": "i",
                                        "in": {
                                            "$substrCP": ["$students", "$$i", 1]
                                        }
                                    }
                                },
                                "as": "char",
                                "cond": {"$eq": ["$$char", "1"]}
                            }
                        }
                    },
                    "total_students": {"$strLenCP": "$students"}
                }
            },

            #lookup subject
            {
                "$lookup": {
                    "from": "subjects",
                    "localField": "active_session.subject.$id",
                    "foreignField": "_id",
                    "as": "subject_data"
                }
            },
            {
                "$unwind": {
                    "path": "$subject_data",
                    "preserveNullAndEmptyArrays": True
                }
            },

            #lookup teacher
            {
                "$lookup": {
                    "from": "teachers",
                    "localField": "active_session.teacher.$id",
                    "foreignField": "_id",
                    "as": "teacher_data"
                }
            },
            {
                "$unwind": {
                    "path": "$teacher_data",
                    "preserveNullAndEmptyArrays": True
                }
            },

            #remove duplicates (important)
            {
                "$group": {
                    "_id": {
                        "teacher": "$teacher_data._id",
                        "start_time": "$active_session.start_time",
                        "end_time": "$active_session.end_time"
                    },
                    "doc": {"$first": "$$ROOT"}
                }
            },
            {
                "$replaceRoot": {"newRoot": "$doc"}
            },

            #final output
            {
                "$project": {
                    "_id": 0,
                    "session_id": {"$toString": "$_id"},
                    "subject_name": "$subject_data.subject_name",
                    "teacher_name": {
                        "$concat": [
                            {"$ifNull": ["$teacher_data.first_name", ""]},
                            " ",
                            {"$ifNull": ["$teacher_data.last_name", ""]}
                        ]
                    },
                    "total_students": 1,
                    "present_students": 1,
                    "session_type": {
                        "$ifNull": ["$subject_data.component", "Lecture"]
                    }
                }
            }
        ]

        results = await Attendance.aggregate(pipeline).to_list()

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Live classes fetched successfully",
                "data": results
            }
        )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"Error fetching live classes: {str(e)}"
            }
        )