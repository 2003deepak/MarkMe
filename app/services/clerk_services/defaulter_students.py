from fastapi import Request, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from typing import Optional
from bson import ObjectId

from app.schemas.student_attendance_summary import StudentAttendanceSummary


async def defaulter_students(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),

    search: Optional[str] = None,
    subject_id: Optional[str] = None,
    program: Optional[str] = None,
    semester: Optional[int] = None,
    threshold: int = Query(75, ge=0, le=100)
):

    user = request.state.user
    role = user.get("role")

    if role not in ["clerk", "admin", "teacher"]:
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Access denied"}
        )

    skip = (page - 1) * limit

    pipeline = []

    #percentage filter
    pipeline.append({
        "$match": {
            "percentage": {"$lt": threshold}
        }
    })

    #join student
    pipeline.append({
        "$lookup": {
            "from": "students",
            "localField": "student.$id",
            "foreignField": "_id",
            "as": "student_data"
        }
    })

    #join subject
    pipeline.append({
        "$lookup": {
            "from": "subjects",
            "localField": "subject.$id",
            "foreignField": "_id",
            "as": "subject_data"
        }
    })

    pipeline += [
        {"$unwind": "$student_data"},
        {"$unwind": "$subject_data"}
    ]

    # ---------------- CLERK SCOPE FILTER ----------------

    if role == "clerk":

        scopes = user.get("academic_scopes", [])

        if not scopes:
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "students": [],
                    "total": 0
                }
            )

        scope_filters = []

        for scope in scopes:
            scope_filters.append({
                "student_data.program": scope["program_id"],
                "student_data.department": scope["department_id"]
            })

        pipeline.append({
            "$match": {
                "$or": scope_filters
            }
        })

    # ---------------- OPTIONAL FILTERS ----------------

    if program:
        pipeline.append({
            "$match": {
                "student_data.program": program
            }
        })

    if semester:
        pipeline.append({
            "$match": {
                "student_data.semester": semester
            }
        })

    # ---------------- GROUP BY STUDENT ----------------

    pipeline.append({
        "$group": {

            "_id": "$student_data._id",

            "name": {
                "$first": {
                    "$concat": [
                        "$student_data.first_name",
                        " ",
                        "$student_data.last_name"
                    ]
                }
            },

            "profile_picture": {"$first": "$student_data.profile_picture"},

            "roll": {"$first": "$student_data.roll_number"},
            "program": {"$first": "$student_data.program"},
            "semester": {"$first": "$student_data.semester"},

            "overall_percentage": {"$avg": "$percentage"},

            "defaulter_subjects": {
                "$push": {
                    "id": "$subject_data._id",
                    "name": "$subject_data.subject_name",
                    "percentage": "$percentage",
                    "code": "$subject_data.subject_code"
                }
            }
        }
    })

    # ---------------- SEARCH ----------------

    if search:
        pipeline.append({
            "$match": {
                "name": {
                    "$regex": search,
                    "$options": "i"
                }
            }
        })

    # ---------------- SUBJECT FILTER ----------------

    if subject_id:

        pipeline.append({
            "$addFields": {
                "defaulter_subjects": {
                    "$filter": {
                        "input": "$defaulter_subjects",
                        "as": "sub",
                        "cond": {
                            "$eq": ["$$sub.id", ObjectId(subject_id)]
                        }
                    }
                }
            }
        })

        pipeline.append({
            "$match": {
                "defaulter_subjects.0": {"$exists": True}
            }
        })

    # ---------------- RISK CALCULATION ----------------

    pipeline.append({
        "$addFields": {
            "risk": {
                "$cond": [
                    {"$lt": ["$overall_percentage", 65]},
                    "HIGH",
                    "MEDIUM"
                ]
            }
        }
    })

    # ---------------- PROJECTION ----------------

    pipeline.append({
        "$project": {

            "_id": 0,

            "student_id": {"$toString": "$_id"},
            "profile_picture": 1,
            "name": 1,
            "roll": 1,
            "program": 1,
            "semester": 1,

            "overall_percentage": {
                "$round": ["$overall_percentage", 2]
            },

            "defaulter_subjects": {
                "$map": {
                    "input": "$defaulter_subjects",
                    "as": "s",
                    "in": {
                        "id": {"$toString": "$$s.id"},
                        "name": "$$s.name",
                        "percentage": "$$s.percentage",
                        "code": "$$s.code"
                    }
                }
            },

            "risk": 1
        }
    })

    pipeline.append({
        "$sort": {"_id": 1}
    })

    #pagination
    pipeline.append({
        "$facet": {
            "data": [
                {"$skip": skip},
                {"$limit": limit}
            ],
            "total": [
                {"$count": "count"}
            ]
        }
    })

    result = await StudentAttendanceSummary.aggregate(pipeline).to_list(None)

    data = result[0]["data"]
    total = result[0]["total"][0]["count"] if result[0]["total"] else 0

    return JSONResponse(
        status_code=200,
        content=jsonable_encoder({
            "success": True,
            "page": page,
            "limit": limit,
            "total": total,
            "students": data
        })
    )