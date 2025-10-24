from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from app.core.redis import redis_client
from bson import ObjectId
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from app.schemas.student_attendance_summary import StudentAttendanceSummary
from app.schemas.attendance import Attendance
from app.schemas.session import Session
from app.schemas.subject import Subject


# JSON encoder to handle ObjectId and datetime
class MongoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


async def get_student_subject_wise(
    
    request : Request,
    student_id: Optional[str],
    subject_id: str,
    month: Optional[int],
    year: Optional[int],
    
) -> Dict[str, Any]:
    user_role = request.state.user.get("role")

    # --- Role-based auth ---
    allowed_roles = {"student", "clerk", "admin", "teacher"}
    if user_role not in allowed_roles:
        raise HTTPException(
            status_code=403,
            detail={"success": False, "message": f"Role '{user_role}' not authorized"}
        )

    # --- Resolve student ID ---
    if user_role == "student":
        target_id = str(request.state.user.get("id"))
        if not target_id:
            raise HTTPException(
                status_code=400,
                detail={"success": False, "message": "Student ID missing in token"}
            )
    else:
        target_id = student_id

    # --- Cache key includes month & year for uniqueness ---
    cache_key = f"student_subject_attendance:{target_id}:{subject_id}:{month}:{year}"
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        try:
            return {
                "success": True,
                "data": json.loads(cached_data),
                "source": "cache"
            }
        except json.JSONDecodeError:
            await redis_client.delete(cache_key)

    try:
        summary = await StudentAttendanceSummary.find_one(
            StudentAttendanceSummary.student.id == ObjectId(target_id),
            StudentAttendanceSummary.subject.id == ObjectId(subject_id),
            fetch_links=True
        )

        if not summary:
            
            return JSONResponse(status_code=200, 
                         content={
                            "success": True,
                            "data": {
                                "subject_id": subject_id,
                                "subject_name": "Unknown",
                                "component": None,
                                "total_classes": 0,
                                "attended": 0,
                                "percentage": 0,
                                "present_sessions": [],
                                "absent_sessions": []
                            },
                            "source": "database"
            })
            

        # --- Filter helper based on month & year ---
        def in_selected_month(date_obj: Optional[datetime]) -> bool:
            if not date_obj:
                return False
            if month and date_obj.month != month:
                return False
            if year and date_obj.year != year:
                return False
            return True

        # --- Present Sessions ---
        present_sessions = []
        if summary.sessions_present:
            for dbref in summary.sessions_present:
                attendance = await Attendance.get(ObjectId(dbref.id), fetch_links=True)
                if attendance and attendance.session:
                    if in_selected_month(attendance.date):
                        session = attendance.session
                        present_sessions.append({
                            "attendance_id": str(attendance.id),
                            "date": attendance.date.isoformat() if attendance.date else None,
                            "day": session.day if session else None,
                            "session_id": str(session.id) if session else None,
                            "start_time": session.start_time if session else None,
                            "end_time": session.end_time if session else None,
                            "type": "present"
                        })

        # --- Absent Sessions ---
        all_attendances = await Attendance.find(
            Attendance.session.subject.id == summary.subject.id,
            fetch_links=True
        ).to_list()

        absent_sessions = []
        present_ids = {p["attendance_id"] for p in present_sessions}

        for att in all_attendances:
            if str(att.id) not in present_ids and att.session:
                if in_selected_month(att.date):
                    session = att.session
                    absent_sessions.append({
                        "attendance_id": str(att.id),
                        "date": att.date.isoformat() if att.date else None,
                        "day": session.day if session else None,
                        "session_id": str(session.id) if session else None,
                        "start_time": session.start_time if session else None,
                        "end_time": session.end_time if session else None,
                        "type": "absent"
                    })

        # --- Summary ---
        total_classes = len(present_sessions) + len(absent_sessions)
        attended = len(present_sessions)
        percentage = round((attended / total_classes) * 100, 2) if total_classes > 0 else 0

        result = {
            "subject_id": str(summary.subject.id),
            "subject_name": summary.subject.subject_name if summary.subject else "Unknown",
            "component": summary.subject.component if summary.subject else None,
            "total_classes": total_classes,
            "attended": attended,
            "percentage": percentage,
            "present_sessions": present_sessions,
            "absent_sessions": absent_sessions
        }

        # --- Cache it ---
        await redis_client.setex(cache_key, 1800, json.dumps(result, cls=MongoJSONEncoder))
        
        return JSONResponse(status_code=200, content=result)


    except Exception as e:
        logging.error(f"💥 Error fetching subject-wise attendance: {e}")
        
        return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "message": "Failed to fetch subject-wise attendance",

                }
            )
        