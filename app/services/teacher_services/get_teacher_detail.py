from decimal import Decimal
from statistics import mean
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from app.core.redis import get_redis_client
from bson import ObjectId
import json
from datetime import datetime, timedelta
from pydantic import HttpUrl
from app.schemas.attendance import Attendance
from app.schemas.exception_session import ExceptionSession
from app.schemas.session import Session
from app.schemas.subject_session_stats import SubjectSessionStats
from beanie.operators import In
from app.schemas.teacher import Teacher
from app.models.allModel import TeacherShortView
from app.schemas.teacher_subject_summary import TeacherSubjectSummary


import logging
# Setup logger for this module
logger = logging.getLogger(__name__)


class MongoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, HttpUrl):
            return str(obj)
        return super().default(obj)


async def get_teacher_me(request: Request):

    user = request.state.user

    if user.get("role") != "teacher":
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "message": "Only teachers can access this route"
            }
        )

    teacher_email = user.get("email")
    redis = await get_redis_client()

    cache_key = f"teacher:profile:{teacher_email}"

    cached = await redis.get(cache_key)

    if cached:
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Teacher details fetched successfully",
                "data": json.loads(cached)
            }
        )

    # ---------------- AGGREGATION PIPELINE ----------------

    pipeline = [

        #find teacher
        {
            "$match": {
                "email": teacher_email
            }
        },

        #join subjects taught by teacher
        {
            "$lookup": {
                "from": "subjects",
                "localField": "_id",
                "foreignField": "teacher_assigned.$id",
                "as": "subjects"
            }
        },

        {
            "$unwind": {
                "path": "$subjects",
                "preserveNullAndEmptyArrays": True
            }
        },

        #fetch program information
        {
            "$lookup": {
                "from": "programs",
                "localField": "subjects.program",
                "foreignField": "_id",
                "as": "program_info"
            }
        },

        {
            "$unwind": {
                "path": "$program_info",
                "preserveNullAndEmptyArrays": True
            }
        },

        #group everything
        {
            "$group": {

                "_id": "$_id",

                "teacher_id": {"$first": "$teacher_id"},
                "first_name": {"$first": "$first_name"},
                "middle_name": {"$first": "$middle_name"},
                "last_name": {"$first": "$last_name"},
                "email": {"$first": "$email"},
                "mobile_number": {"$first": "$mobile_number"},
                "profile_picture": {"$first": "$profile_picture"},

                #subjects list
                "subjects": {
                    "$addToSet": {
                        "subject_id": {"$toString": "$subjects._id"},
                        "subject_code": "$subjects.subject_code",
                        "subject_name": "$subjects.subject_name",
                        "program": "$subjects.program",
                        "department": "$subjects.department",
                        "semester": "$subjects.semester",
                        "component": "$subjects.component"
                    }
                },

                #scope (program + department)
                "scope": {
                    "$addToSet": {
                        "program": "$subjects.program",
                        "department": "$subjects.department"
                    }
                }
            }
        },

        {
            "$project": {
                "_id": 0,
                "teacher_id": 1,
                "first_name": 1,
                "middle_name": 1,
                "last_name": 1,
                "email": 1,
                "mobile_number": 1,
                "profile_picture": 1,
                "subjects": 1,
                "scope": 1
            }
        }

    ]

    result = await Teacher.aggregate(pipeline).to_list(length=1)

    if not result:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "message": "Teacher not found"
            }
        )

    teacher_data = result[0]

    teacher_json = json.dumps(teacher_data, cls=MongoJSONEncoder)

    #cache for 1 hour
    await redis.setex(cache_key, 3600, teacher_json)

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "Teacher details fetched successfully",
            "data": json.loads(teacher_json)
        }
    )


# 2. Get Teacher Details by ID (used by Clerk)
async def get_teacher_by_id(request: Request,teacher_id: str):
    
    # AUTH
    user_role = request.state.user.get("role")
    if user_role != "clerk":
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Only clerks can access this route"}
        )

    # FETCH SUBJECT SUMMARIES
    summaries = await TeacherSubjectSummary.find(
        TeacherSubjectSummary.teacher.id == ObjectId(teacher_id),
        fetch_links=True
    ).to_list()

    if not summaries:
        return JSONResponse(
            status_code=404,
            content={"success": False, "message": "No subject data found for teacher"}
        )


    # KPI CALCULATION
    subjects_count = len(summaries)
    total_sessions = 0
    weighted_attendance_sum = Decimal("0")
    risk_students = 0

    subjects_data = []

    for s in summaries:
        sessions = s.total_sessions_conducted
        avg_att = Decimal(str(s.average_attendance_percentage))

        total_sessions += sessions
        weighted_attendance_sum += avg_att * sessions
        risk_students += (s.defaulter_count + s.at_risk_count)

        # Status logic
        if avg_att >= 80:
            status = "GOOD"
        elif avg_att >= 65:
            status = "WARNING"
        else:
            status = "CRITICAL"

        subjects_data.append({
            "subject_id": str(s.subject.id),
            "subject_name": s.subject.subject_name,
            "component" : s.subject.component,
            "average_attendance": float(avg_att),
            "total_sessions": sessions,
            "status": status
        })

    average_attendance = (
        float(weighted_attendance_sum / total_sessions)
        if total_sessions > 0 else 0
    )

    # RESPONSE
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "kpis": {
                "subjects_count": subjects_count,
                "average_attendance": round(average_attendance, 2),
                "total_sessions": total_sessions,
                "risk_students": risk_students
            },
            "subjects": subjects_data
        }
    )

async def get_teacher_subject_performance(
    request: Request,
    teacher_id: str,
    subject_id: str
):
    logger.info(
        f"Starting get_teacher_subject_performance: teacher_id={teacher_id}, subject_id={subject_id}"
    )

    try:
        # --------------------------------------------------
        # 1️⃣ AUTHORIZATION
        # --------------------------------------------------
        if request.state.user.get("role") != "clerk":
            return JSONResponse(
                status_code=403,
                content={"success": False, "message": "Only clerks can access this route"}
            )

        teacher_oid = ObjectId(teacher_id)
        subject_oid = ObjectId(subject_id)

        # --------------------------------------------------
        # 2️⃣ SUBJECT SUMMARY (SOURCE OF TRUTH)
        # --------------------------------------------------
        summary = await TeacherSubjectSummary.find_one(
            TeacherSubjectSummary.teacher.id == teacher_oid,
            TeacherSubjectSummary.subject.id == subject_oid,
            fetch_links=True
        )

        if not summary:
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": "Subject summary not found"}
            )

        avg_attendance = Decimal(str(summary.average_attendance_percentage))
        total_sessions = summary.total_sessions_conducted
        risk_students = summary.defaulter_count + summary.at_risk_count

        if avg_attendance >= 80:
            status = "GOOD"
        elif avg_attendance >= 65:
            status = "WARNING"
        else:
            status = "CRITICAL"

        # --------------------------------------------------
        # 3️⃣ TIMETABLE SESSIONS (PLANNED)
        # --------------------------------------------------
        sessions = await Session.find(
            Session.teacher.id == teacher_oid,
            Session.subject.id == subject_oid,
            Session.is_active == True
        ).to_list()

        session_ids = [s.id for s in sessions]

        # --------------------------------------------------
        # 4️⃣ ADDITIONAL (ADD) EXCEPTION SESSIONS
        # --------------------------------------------------
        added_exceptions = await ExceptionSession.find(
            ExceptionSession.action == "Add",
            ExceptionSession.teacher.id == teacher_oid,
            ExceptionSession.subject.id == subject_oid
        ).to_list()

        added_exception_ids = [ex.id for ex in added_exceptions]

        # --------------------------------------------------
        # 5️⃣ ATTENDANCE (NORMAL + ADD)
        # --------------------------------------------------
        attendance_ids = []

        # Normal / Rescheduled attendance
        if session_ids:
            normal_attendance = await Attendance.find(
                In(Attendance.session.id, session_ids)
            ).to_list()

            attendance_ids.extend([a.id for a in normal_attendance])

        # Added-session attendance
        if added_exception_ids:
            added_attendance = await Attendance.find(
                In(Attendance.exception_session.id, added_exception_ids)
            ).to_list()

            attendance_ids.extend([a.id for a in added_attendance])

        # --------------------------------------------------
        # 6️⃣ ATTENDANCE TREND (NORMAL + ADD)
        # --------------------------------------------------
        attendance_trend = []

        if attendance_ids:
            stats = await SubjectSessionStats.find(
                SubjectSessionStats.subject.id == subject_oid,
                In(SubjectSessionStats.session_id.id, attendance_ids)
            ).sort("date").to_list()

            attendance_trend = [
                {
                    "date": stat.date.date().isoformat(),
                    "attendance": round(stat.percentage_present, 2)
                }
                for stat in stats
            ]

        # --------------------------------------------------
        # 7️⃣ COMPONENT (SAFE)
        # --------------------------------------------------
        component = summary.subject.component if summary.subject else "Unknown"

        # --------------------------------------------------
        # 8️⃣ SESSION HEALTH
        # --------------------------------------------------
        cancelled_sessions = 0
        rescheduled_sessions = 0

        if session_ids:
            exception_sessions = await ExceptionSession.find(
                In(ExceptionSession.session.id, session_ids)
            ).to_list()

            for ex in exception_sessions:
                if ex.action == "Cancel":
                    cancelled_sessions += 1
                elif ex.action == "Rescheduled":
                    rescheduled_sessions += 1

        newly_added_sessions = len(added_exception_ids)

        planned_sessions = len(sessions)
        conducted_sessions = total_sessions  # summary-driven (correct)

        # --------------------------------------------------
        # 9️⃣ RESPONSE
        # --------------------------------------------------
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "subject_info": {
                    "subject_id": str(summary.subject.id),
                    "subject_name": summary.subject.subject_name,
                    "component": component,
                    "status": status
                },
                "kpis": {
                    "average_attendance": float(avg_attendance),
                    "total_sessions": conducted_sessions,
                    "risk_students": risk_students
                },
                "attendance_trend": attendance_trend,
                "session_health": {
                    "weekly_slots": planned_sessions,
                    "conducted_sessions": conducted_sessions,
                    "cancelled_sessions": cancelled_sessions,
                    "rescheduled_sessions": rescheduled_sessions,
                    "additional_sessions": newly_added_sessions
                }
            }
        )

    except Exception:
        logger.exception("Unexpected error in get_teacher_subject_performance")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "Internal server error"}
        )
        
        
async def get_teacher_subject_insights(
    request: Request,
    teacher_id: str,
    subject_id: str
):
    try:
        # --------------------------------------------------
        # 1️⃣ AUTHORIZATION
        # --------------------------------------------------
        if request.state.user.get("role") != "clerk":
            return JSONResponse(
                status_code=403,
                content={"success": False, "message": "Only clerks can access this route"}
            )

        teacher_oid = ObjectId(teacher_id)
        subject_oid = ObjectId(subject_id)

        # --------------------------------------------------
        # 2️⃣ LOAD SUBJECT SUMMARY (FOR RISK CONTEXT)
        # --------------------------------------------------
        summary = await TeacherSubjectSummary.find_one(
            TeacherSubjectSummary.teacher.id == teacher_oid,
            TeacherSubjectSummary.subject.id == subject_oid
        )

        if not summary:
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": "Subject summary not found"}
            )

        # --------------------------------------------------
        # 3️⃣ LOAD ATTENDANCE TREND DATA
        # --------------------------------------------------
        stats = await SubjectSessionStats.find(
            SubjectSessionStats.subject.id == subject_oid
        ).sort("date").to_list()

        if len(stats) < 10:
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "insights": [
                        {
                            "text": "Not enough session data to generate reliable insights.",
                            "severity": "INFO"
                        }
                    ],
                    "metrics": {}
                }
            )

        attendance = [s.percentage_present for s in stats]

        # --------------------------------------------------
        # 4️⃣ DERIVED METRICS
        # --------------------------------------------------
        min_att = min(attendance)
        max_att = max(attendance)
        volatility = max_att - min_att

        low_attendance_sessions = sum(1 for a in attendance if a < 60)

        last_5_avg = mean(attendance[-5:])
        prev_5_avg = mean(attendance[-10:-5])
        trend_delta = last_5_avg - prev_5_avg

        insights = []

        # --------------------------------------------------
        # 5️⃣ INSIGHT RULES (DETERMINISTIC)
        # --------------------------------------------------

        # 🔹 Volatility Insight
        if volatility >= 30:
            insights.append({
                "text": (
                    f"Attendance shows extreme fluctuations (±{round(volatility / 2, 1)}%), "
                    "indicating inconsistent student engagement."
                ),
                "severity": "WARNING"
            })

        # 🔹 Low Attendance Pattern
        if low_attendance_sessions >= 5:
            insights.append({
                "text": (
                    f"Low attendance (<60%) occurred in {low_attendance_sessions} sessions, "
                    "suggesting recurring disengagement rather than isolated incidents."
                ),
                "severity": "WARNING"
            })

        # 🔹 Trend Direction
        if trend_delta > 3:
            insights.append({
                "text": (
                    f"Attendance improved by +{round(trend_delta, 1)}% over the last 5 sessions "
                    "compared to the previous 5."
                ),
                "severity": "INFO"
            })
        elif trend_delta < -3:
            insights.append({
                "text": (
                    f"Attendance declined by {abs(round(trend_delta, 1))}% over the last 5 sessions "
                    "compared to the previous 5."
                ),
                "severity": "CRITICAL"
            })
        else:
            insights.append({
                "text": "Attendance has remained relatively stable in recent sessions.",
                "severity": "INFO"
            })

        # 🔹 Stability vs Improvement Conflict
        if trend_delta > 3 and volatility >= 30:
            insights.append({
                "text": (
                    "Despite recent improvement, attendance remains unstable, "
                    "indicating gains may not be sustained without intervention."
                ),
                "severity": "WARNING"
            })

        # 🔹 Risk Students Insight
        risk_students = summary.defaulter_count + summary.at_risk_count
        if risk_students >= 0.25 * summary.total_sessions_conducted:
            insights.append({
                "text": (
                    "A high number of at-risk students has been identified — "
                    "academic or attendance intervention is recommended."
                ),
                "severity": "CRITICAL"
            })

        # --------------------------------------------------
        # 6️⃣ RESPONSE
        # --------------------------------------------------
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "insights": insights,
                "metrics": {
                    "min_attendance": round(min_att, 2),
                    "max_attendance": round(max_att, 2),
                    "volatility": round(volatility, 2),
                    "last_5_avg": round(last_5_avg, 2),
                    "previous_5_avg": round(prev_5_avg, 2),
                    "trend_delta": round(trend_delta, 2),
                    "low_attendance_sessions": low_attendance_sessions
                }
            }
        )

    except Exception:
        logger.exception("Error generating subject insights")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "Internal server error"}
        )
