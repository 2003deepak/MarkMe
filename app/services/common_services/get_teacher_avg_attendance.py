from fastapi import HTTPException, Request
from bson import ObjectId
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from fastapi.responses import JSONResponse
from app.schemas.teacher_subject_summary import TeacherSubjectSummary  

# --- JSON encoder for ObjectId & datetime ---
class MongoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


async def get_teacher_avg_attendance(
    request: Request, 
    department_name: str, 
    program: Optional[str] = None, 
    semester: Optional[int] = None
) -> Dict[str, Any]:
    try:
        user_role = request.state.user.get("role")
        if user_role not in {"admin", "clerk"}:
            raise HTTPException(status_code=403, detail="Unauthorized access")

        # logging.info(f"🔍 Starting aggregation for department: {department_name}")
        # logging.info(f"👤 User role: {user_role}")
        # logging.info(f"📚 Program filter: {program}")
        # logging.info(f"📖 Semester filter: {semester}")

        # --- Main aggregation pipeline ---
        pipeline = [
            {
                "$lookup": {
                    "from": "teachers",
                    "localField": "teacher.$id",
                    "foreignField": "_id",
                    "as": "teacher_info"
                }
            },
            {"$unwind": "$teacher_info"},
            {
                "$lookup": {
                    "from": "subjects",
                    "localField": "subject.$id",
                    "foreignField": "_id",
                    "as": "subject_info"
                }
            },
            {"$unwind": "$subject_info"},
            {
                "$match": {
                    "teacher_info.department": department_name
                }
            },
            {
                "$project": {
                    "_id": 0,
                    # ✅ Combine teacher full name properly (handles missing middle name without double spaces)
                    "teacher_name": {
                        "$concat": [
                            "$teacher_info.first_name",
                            " ",
                            {
                                "$ifNull": [
                                    {
                                        "$concat": [
                                            "$teacher_info.middle_name",
                                            " "
                                        ]
                                    },
                                    ""
                                ]
                            },
                            "$teacher_info.last_name"
                        ]
                    },
                    "subject_name": "$subject_info.subject_name",
                    "subject_type": "$subject_info.component",
                    "program" : "$subject_info.program",
                    "semester" : "$subject_info.semester",
                    "total_sessions_conducted": "$total_sessions_conducted",
                    "average_attendance_percentage": {
                        "$toDouble": "$average_attendance_percentage"
                    }
                }
            }
        ]

        # --- Add conditional match stages for program and semester ---
        match_conditions = {"teacher_info.department": department_name}
        if program:
            match_conditions["subject_info.program"] = program
        if semester is not None:
            match_conditions["subject_info.semester"] = semester

        # Insert the full match after lookups and unwinds
        pipeline.insert(4, {"$match": match_conditions})

        # Add sort at the end
        pipeline.append({"$sort": {"teacher_name": 1}})

        # logging.info(f"📋 Pipeline stages: {len(pipeline)} stages")
        # logging.info(f"🔍 Match conditions: {match_conditions}")

        results = await TeacherSubjectSummary.aggregate(pipeline).to_list(None)
        # logging.info(f"📊 Raw results count: {len(results)}")
        # if results:
        #     logging.info(f"📋 Sample result (first): {json.dumps(results, cls=MongoJSONEncoder, indent=2)}")
        # else:
        #     logging.info("⚠️ No results found after aggregation")

        if not results:
            message_parts = [f"department '{department_name}'"]
            if program:
                message_parts.append(f"program '{program}'")
            if semester is not None:
                message_parts.append(f"semester {semester}")
            message = f"No teacher attendance data found for " + ", ".join(message_parts)
            response = {
                "status": "fail",
                "message": message
            }
            # logging.warning(f"🚨 No data for filters: {match_conditions}"
        
            return JSONResponse(
                status_code=200,  
                content={
                    "status": "success",
                    "message": "No data Found",
                    "data": response_data
                }
            )

        # --- Compute filtered summary ---
        avg_attendance = round(
            sum(r["average_attendance_percentage"] for r in results) / len(results), 2
        )
        unique_teachers = len(set(r["teacher_name"] for r in results))

        # --- Prepare response ---
        response_data = {
            "department": department_name,
            "program": program,
            "semester": semester,
            "department_average": avg_attendance,
            "total_teachers": unique_teachers,
            "teacher_summary": results
        }
        
        return JSONResponse(
            status_code=200,  
            content={
                "status": "success",
                "message": "Teacher avg class attendance fetched successfully",
                "data": response_data
            }
        )


    except Exception as e:
        # Log full stack trace
        logging.exception(f"💥 Error fetching teacher summary for {department_name}: {e}")
        return JSONResponse(
            status_code=500,  
            content={
                "status": "fail",
                "message": str(e),
               
            }
        )