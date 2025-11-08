from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from typing import Dict, Any, Optional
from bson import ObjectId
import json, logging
from datetime import datetime
from app.core.redis import redis_client
from app.schemas.student_attendance_summary import StudentAttendanceSummary

class MongoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        from bson import ObjectId
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


async def get_student_attendance_summary(request: Request, student_id: Optional[str]) -> Dict[str, Any]:
    user = request.state.user
    user_role = user.get("role")
    user_id = user.get("id")
    
    print("The user is = " , user)

    allowed_roles = {"student", "clerk", "admin", "teacher"}
    if user_role not in allowed_roles:
        raise HTTPException(
            status_code=403,
            detail={
                "success": False,
                "message": f"Access denied. Role '{user_role}' not authorized to view attendance summaries"
            }
        )

    # ✅ Determine target student ID based on role
    if user_role == "student":
        student_id = user_id
        print(f"🎓 Student viewing own attendance → {student_id}")
    elif not student_id:
        raise HTTPException(
            status_code=400,
            detail={
                "success": False,
                "message": "Missing required 'student_id' query parameter for clerk/teacher/admin."
            }
        )
    else:
        print(f"🧾 {user_role.capitalize()} fetching attendance for student → {student_id}")

    # 3. Check Redis cache
    cache_key = f"student_attendance_summary:{student_id}:{user_role}"
    cached_data = await redis_client.get(cache_key)

    if cached_data:
        try:
            response_content = {
                "success": True,
                "message": "Student attendance fetched successfully",
                "data": json.loads(cached_data),
                "source": "cache"
            }
            return JSONResponse(status_code=200, content=response_content)
        except json.JSONDecodeError:
            await redis_client.delete(cache_key)

    # 4. Fetch from DB
    try:
        summaries = await StudentAttendanceSummary.find(
            StudentAttendanceSummary.student.id == ObjectId(student_id),
            fetch_links=True
        ).to_list()

        result = []
        total_classes = total_attended = 0
        lab_total = lab_attended = 0
        lecture_total = lecture_attended = 0

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

        # cache result for 30 mins
        await redis_client.setex(cache_key, 1800, json.dumps(data))

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Student attendance fetched successfully",
                "data": data,
                "source": "database"
            },
        )

    except Exception as e:
        logging.error(f"💥 Error fetching attendance summary: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "Failed to fetch attendance summary due to server error",
            },
        )
