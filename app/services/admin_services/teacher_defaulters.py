from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from app.core.redis import redis_client
from datetime import datetime
from fastapi.encoders import jsonable_encoder
from bson import ObjectId

from app.schemas.attendance import Attendance


async def teacher_defaulters(request : Request , page: int =1 , limit: int =10):
    
    user_role = request.state.user.get("role")

    if user_role != "admin":

        return JSONResponse(
        status_code=403,
        content={
            "success": False,
            "message": "Only Admin can access this route",
            
        }
    )
        
        
    skip = (page - 1) * limit

    pipeline = []

    #student join
    pipeline.append({
    
        "$lookup": {
            "from": "students",
            "localField": "student.$id",
            "foreignField": "_id",
            "as": "student_data"
        }
    })

    #subject join
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


    #group by student
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
            
            "profile_picture" : { "$first" : "$student_data.profile_picture"},

            "roll": {"$first": "$student_data.roll_number"},

            "program": {"$first": "$student_data.program"},
            "semester": {"$first": "$student_data.semester"},

            "overall_percentage": {
                "$avg": "$percentage"
            },

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

    #search by student name
    if search:
        pipeline.append({
            "$match": {
                "name": {
                    "$regex": search,
                    "$options": "i"
                }
            }
        })

    #subject filter inside grouped result
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

    #risk calculation
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

    #projection
    pipeline.append({
    "$project": {
        "_id": 0,

        "student_id": {
            "$toString": "$_id"
        },
        "profile_picture" : 1 ,
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
                    "id": { "$toString": "$$s.id" },
                    "name": "$$s.name",
                    "percentage": "$$s.percentage",
                    "code": "$$s.code"
                }
            }
        },

        "risk": 1
    }
})

    #pagination facet
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

    result = await Attendance.aggregate(pipeline).to_list(None)

    data = result[0]["data"]
    total = result[0]["total"][0]["count"] if result[0]["total"] else 0

    
  
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "Clerk fetched successfully",
            "data": jsonable_encoder(
                result,
                custom_encoder={ObjectId: str, datetime: lambda x: x.isoformat()}
            )
            
        })