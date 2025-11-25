from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from typing import Dict, Any, Optional
from bson import ObjectId
import json, logging
from datetime import datetime

from app.core.redis import redis_client
from app.schemas.student_attendance_summary import StudentAttendanceSummary
from app.schemas.subject import Subject         
from app.schemas.student import Student         

# --------------------------------------------------------------------------- #
# Custom JSON encoder for MongoDB types
# --------------------------------------------------------------------------- #
class MongoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


# --------------------------------------------------------------------------- #
# Endpoint
# --------------------------------------------------------------------------- #
async def get_student_attendance_summary(
    request: Request, student_id: Optional[str]
) -> JSONResponse:
    user = request.state.user
    user_role = user.get("role")
    user_id = user.get("id")
    program = user.get("program")
    semester = user.get("semester")

    print("The user is =", user)

    allowed_roles = {"student", "clerk", "admin", "teacher"}
    if user_role not in allowed_roles:
        raise HTTPException(
            status_code=403,
            detail={
                "success": False,
                "message": f"Access denied. Role '{user_role}' not authorized to view attendance summaries"
            },
        )

    # --------------------------------------------------------------- #
    # 1. Resolve the target student_id
    # --------------------------------------------------------------- #
    if user_role == "student":
        student_id = user_id
        print(f"Student viewing own attendance → {student_id}")
    elif not student_id:
        raise HTTPException(
            status_code=400,
            detail={
                "success": False,
                "message": "Missing required 'student_id' query parameter for clerk/teacher/admin."
            },
        )
    else:
        print(f"{user_role.capitalize()} fetching attendance for student → {student_id}")

    # --------------------------------------------------------------- #
    # 2. Redis cache
    # --------------------------------------------------------------- #
    cache_key = f"student_attendance_summary:{student_id}:{user_role}"
    cached_data = await redis_client.get(cache_key)

    if cached_data:
        try:
            cached_json = json.loads(cached_data)
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "message": "Student attendance fetched successfully",
                    "data": cached_json,
                    "source": "cache",
                },
            )
        except json.JSONDecodeError:
            await redis_client.delete(cache_key)
            logging.warning(f"Invalid cache data for key: {cache_key}, cleared.")

    # --------------------------------------------------------------- #
    # 3. DB work
    # --------------------------------------------------------------- #
    try:
        # -----------------------------------------------------------
        # 3.1 Get the student document (need program + semester)
        # -----------------------------------------------------------
        student_doc = await Student.find_one(
            Student.id == ObjectId(student_id)
        )
        if not student_doc:
            raise HTTPException(
                status_code=404,
                detail={"success": False, "message": "Student not found"}
            )

        # For non-student callers we still need program/semester → fall back to request user
        prog = getattr(student_doc, "program", program)
        sem = getattr(student_doc, "semester", semester)

        if not prog or not sem:
            raise HTTPException(
                status_code=400,
                detail={"success": False, "message": "Student program/semester missing"}
            )

        # -----------------------------------------------------------
        # 3.2 Fetch **ALL** subjects for this program + semester
        # -----------------------------------------------------------
        all_subjects = await Subject.find(
            Subject.program == prog,
            Subject.semester == sem
        ).to_list()

        if not all_subjects:
            raise HTTPException(
                status_code=404,
                detail={"success": False, "message": "No subjects defined for this program/semester"}
            )

        # -----------------------------------------------------------
        # 3.3 Fetch existing attendance summaries (if any)
        # -----------------------------------------------------------
        summaries = await StudentAttendanceSummary.find(
            StudentAttendanceSummary.student.id == ObjectId(student_id),
            fetch_links=True,
        ).to_list()

        # Build a quick lookup: subject_id → summary
        summary_map: Dict[str, StudentAttendanceSummary] = {
            str(s.subject.id): s for s in summaries if getattr(s, "subject", None)
        }

        # -----------------------------------------------------------
        # 3.4 Build the response list
        # -----------------------------------------------------------
        result = []
        total_classes = total_attended = 0
        lab_total = lab_attended = 0
        lecture_total = lecture_attended = 0

        for subj in all_subjects:
            subj_id = str(subj.id)
            component = getattr(subj, "component", "Lecture")

            # Use summary if exists, otherwise zeros
            if subj_id in summary_map:
                summ = summary_map[subj_id]
                total = summ.total_classes or 0
                attended = summ.attended or 0
                perc = round(summ.percentage, 2) if summ.percentage is not None else 0.0
            else:
                total = attended = 0
                perc = 0.0

            entry = {
                "subject_name": getattr(subj, "subject_name", "Unknown Subject"),
                "component": component,
                "total_classes": total,
                "attended": attended,
                "percentage": perc,
            }
            result.append(entry)

            # aggregate totals
            total_classes += total
            total_attended += attended
            if component == "Lab":
                lab_total += total
                lab_attended += attended
            elif component == "Lecture":
                lecture_total += total
                lecture_attended += attended

        # -----------------------------------------------------------
        # 3.5 Final percentages
        # -----------------------------------------------------------
        overall_percentage = (
            round((total_attended / total_classes * 100), 2) if total_classes > 0 else 0.0
        )
        lab_percentage = (
            round((lab_attended / lab_total * 100), 2) if lab_total > 0 else 0.0
        )
        lecture_percentage = (
            round((lecture_attended / lecture_total * 100), 2) if lecture_total > 0 else 0.0
        )

        data = {
            "attendances": result,
            "total_classes": total_classes,
            "total_attended": total_attended,
            "overall_percentage": overall_percentage,
            "lab": {
                "total": lab_total,
                "attended": lab_attended,
                "percentage": lab_percentage,
            },
            "lecture": {
                "total": lecture_total,
                "attended": lecture_attended,
                "percentage": lecture_percentage,
            },
        }

        # -----------------------------------------------------------
        # 3.6 Cache for 30 min
        # -----------------------------------------------------------
        await redis_client.setex(
            cache_key,
            1800,
            json.dumps(data, cls=MongoJSONEncoder),
        )

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Student attendance fetched successfully",
                "data": data,
                "source": "database",
            },
        )

    # ------------------------------------------------------------------- #
    # Error handling
    # ------------------------------------------------------------------- #
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error fetching attendance summary for student {student_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "message": "Failed to fetch attendance summary due to server error",
            },
        )