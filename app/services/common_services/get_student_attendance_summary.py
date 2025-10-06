from fastapi import HTTPException
from pydantic import BaseModel
from app.core.redis import redis_client
from bson import ObjectId, DBRef
import json
import logging
from datetime import datetime
from fastapi.encoders import jsonable_encoder
from bson import ObjectId
from typing import Dict, Any, List, Optional
from app.schemas.student_attendance_summary import StudentAttendanceSummary
from app.schemas.student import Student
from app.schemas.session import Session
from app.schemas.subject import Subject
from app.schemas.attendance import Attendance

# JSON encoder to handle ObjectId and datetime
class MongoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

async def get_student_attendance_summary(student_id: str, user_data: dict) -> Dict[str, Any]:
    user_role = user_data["role"]
    
    print(user_data)
    # 1. ROLE-BASED AUTHORIZATION CHECK
    allowed_roles = {"student", "clerk", "admin", "teacher"}
    if user_role not in allowed_roles:
        raise HTTPException(
            status_code=403,
            detail={
                "status": "fail",
                "message": f"Access denied. Role '{user_role}' not authorized to view attendance summaries"
            }
        )

    print(f"✅ Fetching attendance summary for student {student_id} by role {user_role}")

    # 3. Check cache
    cache_key = f"student_attendance_summary:{student_id}:{user_role}"
    cached_data = await redis_client.get(cache_key)

    if cached_data:
        try:
            return {
                "status": "success",
                "data": json.loads(cached_data),
                "source": "cache"
            }
        except json.JSONDecodeError:
            await redis_client.delete(cache_key)

    # 4. Fetch from database
    try:
        
        print(student_id)
        summaries = await StudentAttendanceSummary.find(
            StudentAttendanceSummary.student.id == ObjectId(student_id),
            fetch_links=True
        ).to_list()

        result = []
        total_classes = 0
        total_attended = 0
        lab_total = 0
        lab_attended = 0
        lecture_total = 0
        lecture_attended = 0
        for summary in summaries:
            component = summary.subject.component if summary.subject else "Unknown"
            result.append({
                "subject_name": summary.subject.subject_name if summary.subject else "Unknown Subject",
                "component": component,
                "total_classes": summary.total_classes,
                "attended": summary.attended,
                "percentage": summary.percentage
            })
            total_classes += summary.total_classes
            total_attended += summary.attended
            if component == "Lab":
                lab_total += summary.total_classes
                lab_attended += summary.attended
            elif component == "Lecture":
                lecture_total += summary.total_classes
                lecture_attended += summary.attended

        overall_percentage = round((total_attended / total_classes * 100), 2) if total_classes > 0 else 0.0
        lab_percentage = round((lab_attended / lab_total * 100), 2) if lab_total > 0 else 0.0
        lecture_percentage = round((lecture_attended / lecture_total * 100), 2) if lecture_total > 0 else 0.0

        data = {
            "attendances": result,
            "total_classes": total_classes,
            "total_attended": total_attended,
            "overall_percentage": overall_percentage,
            "lab": {
                "total": lab_total,
                "attended": lab_attended,
                "percentage": lab_percentage
            },
            "lecture": {
                "total": lecture_total,
                "attended": lecture_attended,
                "percentage": lecture_percentage
            }
        }

        # cache result
        await redis_client.setex(cache_key, 1800, json.dumps(data))

        return {
            "status": "success",
            "data": data,
            "source": "database"
        }

    except Exception as e:
        logging.error(f"💥 Error fetching attendance summary: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "message": "Failed to fetch attendance summary due to server error"
            }
        )