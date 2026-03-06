from datetime import datetime, timezone
from beanie import PydanticObjectId
from bson import DBRef, ObjectId
from fastapi import Request
from fastapi.responses import JSONResponse
from app.schemas.attendance import Attendance
import logging
from beanie.operators import And, In
from typing import List, Optional

from app.schemas.subject import Subject
from app.schemas.subject_session_stats import SubjectSessionStats
from app.utils.parse_data import to_ist

logger = logging.getLogger("attendance_api")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

async def student_attendance_history(
    request: Request,
    month: int,
    year: int,
    subject: Optional[List[str]] = None  # Changed to handle List
):
    logger.info("STUDENT ATTENDANCE HISTORY API CALLED")
    logger.info(f"Params → month={month}, year={year}, subject={subject}")

    user = request.state.user
    if user.get("role") != "student":
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Access denied"}
        )

    roll_no = user.get("roll_number")
    if not roll_no:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Roll number missing"}
        )

    program = user["program"]
    department = user["department"]
    semester = str(user["semester"])
    batch_year = str(user["batch_year"])
    bit_index = roll_no - 1

    # ---------------- DATE RANGE ----------------
    start_date = datetime(year, month, 1)
    end_date = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)

    # ---------------- SESSION FILTER ----------------
    session_match = {
        "session_data.program": program,
        "session_data.department": department,
        "session_data.semester": semester,
        "session_data.academic_year": batch_year,
    }

    # Handle single subject or list of subjects
    if subject:
        # Convert to list if it's a string (backward compatibility)
        if isinstance(subject, str):
            subject_ids = [ObjectId(subject)]
        else:
            # Filter valid ObjectIds
            subject_ids = [ObjectId(sub_id) for sub_id in subject if sub_id and ObjectId.is_valid(sub_id)]
        
        if subject_ids:
            if len(subject_ids) == 1:
                session_match["session_data.subject.$id"] = subject_ids[0]
            else:
                session_match["session_data.subject.$id"] = {"$in": subject_ids}

    # ---------------- AGGREGATION PIPELINE ----------------
    pipeline = [
        # 1️⃣ Exception session
        {
            "$lookup": {
                "from": "exception_sessions",
                "localField": "exception_session.$id",
                "foreignField": "_id",
                "as": "exception"
            }
        },
        {
            "$unwind": {
                "path": "$exception",
                "preserveNullAndEmptyArrays": True
            }
        },

        # 2️⃣ Effective date
        {
            "$addFields": {
                "effective_date": {
                    "$cond": [
                        {"$ifNull": ["$exception", False]},
                        "$exception.date",
                        "$date"
                    ]
                },
                "is_exception_session": {
                    "$cond": [
                        {"$ifNull": ["$exception", False]},
                        True,
                        False
                    ]
                }
            }
        },

        # 3️⃣ Date filter
        {
            "$match": {
                "effective_date": {
                    "$gte": start_date,
                    "$lt": end_date
                }
            }
        },

        # 4️⃣ Base session
        {
            "$addFields": {
                "base_session_id": {
                    "$cond": [
                        {"$ifNull": ["$session", False]},
                        "$session.$id",
                        "$exception.session.$id"
                    ]
                }
            }
        },

        # 5️⃣ Join sessions
        {
            "$lookup": {
                "from": "sessions",
                "localField": "base_session_id",
                "foreignField": "_id",
                "as": "session_data"
            }
        },
        {"$unwind": "$session_data"},

        # 6️⃣ Student eligibility + subject
        {"$match": session_match},

        # 7️⃣ Actual timings
        {
            "$addFields": {
                "actual_start_time": {
                    "$cond": [
                        {"$ifNull": ["$exception.start_time", False]},
                        "$exception.start_time",
                        "$session_data.start_time"
                    ]
                },
                "actual_end_time": {
                    "$cond": [
                        {"$ifNull": ["$exception.end_time", False]},
                        "$exception.end_time",
                        "$session_data.end_time"
                    ]
                }
            }
        },

        # 8️⃣ Join subject
        {
            "$lookup": {
                "from": "subjects",
                "localField": "session_data.subject.$id",
                "foreignField": "_id",
                "as": "subject_data"
            }
        },
        {"$unwind": "$subject_data"},

        # 9️⃣ INTERNAL GROUP (dedup safety)
        {
            "$group": {
                "_id": "$_id",
                "doc": {"$first": "$$ROOT"}
            }
        },
        {"$replaceRoot": {"newRoot": "$doc"}},

        # 🔟 Sort
        {
            "$sort": {
                "effective_date": 1,
                "actual_start_time": 1
            }
        }
    ]

    attendances = await Attendance.aggregate(pipeline).to_list()

    # ---------------- RESPONSE ----------------
    records = []

    for a in attendances:
        subject_data = a.get("subject_data")
        subject_name = subject_data.get("subject_name") if subject_data else "Unknown"

        students_str = a.get("students", "")
        present = (
            len(students_str) > bit_index and students_str[bit_index] == "1"
        )

        ist_date = to_ist(a["effective_date"])
        
        records.append({
            "attendance_id": str(a["_id"]),
            "date": ist_date.date().isoformat(),     
            "day": ist_date.strftime("%A"),  
            "subject": subject_name,
            "component": subject_data.get("component") if subject_data else "Unknown",
            "start_time": a.get("actual_start_time"),
            "end_time": a.get("actual_end_time"),
            "present": present,
            "is_exception_session": a.get("is_exception_session", False)
        })

    total = len(records)
    present_count = sum(1 for r in records if r["present"])
    percentage = round((present_count / total) * 100, 2) if total else 0

    return {
        "success": True,
        "message": "Attendance History Fetched Successfully",
        "records": records
    }


async def teacher_attendance_history(
    request: Request,
    month: int,
    year: int,
    subject: Optional[List[str]] = None  # Changed to handle List
):
    logger.info("TEACHER ATTENDANCE HISTORY API CALLED")
    logger.info(f"Params → month={month}, year={year}, subject={subject}")

    user = request.state.user
    teacher_id = user.get("id")

    if user.get("role") != "teacher":
        return JSONResponse(
            status_code=401,
            content={"success": False, "message": "Access denied"}
        )

    # Convert teacher_id to PydanticObjectId for comparison
    try:
        teacher_obj_id = PydanticObjectId(teacher_id)
    except Exception:
        return JSONResponse(status_code=400, content={"success": False, "message": "Invalid teacher ID"})

    # DATE RANGE
    start_date = datetime(year, month, 1, tzinfo=timezone.utc)
    end_date = (
        datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        if month == 12
        else datetime(year, month + 1, 1, tzinfo=timezone.utc)
    )

    # BASE QUERY
    query = [
        SubjectSessionStats.date >= start_date,
        SubjectSessionStats.date < end_date
    ]

    # SUBJECT FILTER + TEACHER ASSIGNMENT CHECK
    if subject:
        # Convert to list if it's a string (backward compatibility)
        if isinstance(subject, str):
            subject_input = [subject]
        else:
            subject_input = subject
        
        try:
            subject_ids = [PydanticObjectId(sub_id) for sub_id in subject_input if sub_id]
        except Exception:
            return JSONResponse(status_code=400, content={"success": False, "message": "Invalid subject ID"})

        # First, find subjects and check if this teacher is assigned
        subject_docs = await Subject.find(
            In(Subject.id, subject_ids),
            fetch_links=True
        ).to_list()

        if not subject_docs:
            return JSONResponse(status_code=404, content={"success": False, "message": "No subjects found"})

        # Check if the teacher is assigned to all requested subjects
        unauthorized_subjects = []
        for sub in subject_docs:
            if not sub.teacher_assigned or sub.teacher_assigned.id != teacher_obj_id:
                unauthorized_subjects.append(sub.subject_name)

        if unauthorized_subjects:
            return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "message": f"You are not assigned to these subjects: {', '.join(unauthorized_subjects)}"
                }
            )

        # Now safe to filter stats by these subjects
        if len(subject_ids) == 1:
            query.append(SubjectSessionStats.subject.id == subject_ids[0])
        else:
            query.append(In(SubjectSessionStats.subject.id, subject_ids))

    logger.info(f"Final Query → {query}")

    # FETCH
    stats_docs = await SubjectSessionStats.find(
        And(*query),
        fetch_links=True
    ).sort(SubjectSessionStats.date).to_list()

    logger.info(f"Found {len(stats_docs)} records")

    # BUILD RESPONSE
    records = []
    for stat in stats_docs:
        records.append({
            "attendance_id": str(stat.session_id.id),
            "date": stat.date.date().isoformat(),
            "day": stat.date.strftime("%A"),
            "subject": stat.subject.subject_name,
            "component": stat.subject.component,
            "present_count": stat.present_count,
            "absent_count": stat.absent_count,
            "attendance_percentage": stat.percentage_present
        })

    return {
        "success": True,
        "message": "Teacher Attendance History Fetched Successfully",
        "records": records
    }


async def clerk_attendance_history(
    request: Request,
    month: int,
    year: int,
    subject: Optional[List[str]] = None,
    program: Optional[List[str]] = None,
    batch_year: Optional[List[int]] = None,
    semester: Optional[List[int]] = None
):
    
    logger.info(f"Params → month={month}, year={year}, subject={subject}, program={program}, batch_year={batch_year}")

    user = request.state.user
    
    if user.get("role") != "clerk":
        return JSONResponse(
            status_code=401,
            content={"success": False, "message": "Access denied"}
        )

    # ---------------- DATE RANGE ----------------
    start_date = datetime(year, month, 1, tzinfo=timezone.utc)
    end_date = (
        datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        if month == 12
        else datetime(year, month + 1, 1, tzinfo=timezone.utc)
    )

    # ---------------- AGGREGATION PIPELINE ----------------
    pipeline = [
        # 1️⃣ Filter by date first (cheap)
        {
            "$match": {
                "date": {
                    "$gte": start_date,
                    "$lt": end_date
                }
            }
        },

        # 2️⃣ Join → Subject
        {
            "$lookup": {
                "from": "subjects",
                "localField": "subject.$id",
                "foreignField": "_id",
                "as": "subject_data"
            }
        },
        {
            "$unwind": "$subject_data"
        },

        # Teacher Data Joined

        {
            "$lookup": {
                "from": "teachers",
                "localField": "subject_data.teacher_assigned.$id",
                "foreignField": "_id",
                "as": "teacher_data"
            }
        },
        {
            "$unwind": "$teacher_data"
        }
    ]

    # 3️⃣ Optional filters - handle multiple values with $in
    match_stage = {}
    
    # Handle subject filter (can be string or list)
    if subject:
        # Convert to list if it's a string
        if isinstance(subject, str):
            subject_input = [subject]
        else:
            subject_input = subject
        
        # Filter valid ObjectIds
        subject_ids = [ObjectId(sub_id) for sub_id in subject_input if sub_id and ObjectId.is_valid(sub_id)]
        if subject_ids:
            if len(subject_ids) == 1:
                match_stage["subject_data._id"] = subject_ids[0]
            else:
                match_stage["subject_data._id"] = {"$in": subject_ids}
    
    # Handle program filter
    if program:
        # Convert to list if it's a string
        if isinstance(program, str):
            program_input = [program]
        else:
            program_input = program
        
        if len(program_input) == 1:
            match_stage["subject_data.program"] = program_input[0]
        else:
            match_stage["subject_data.program"] = {"$in": program_input}
    
    # Handle batch_year filter
    if batch_year:
        # Convert to list if it's a single integer
        if isinstance(batch_year, int):
            batch_year_input = [batch_year]
        else:
            batch_year_input = batch_year
        
        # Convert batch_year to strings for comparison
        batch_years_str = [str(year) for year in batch_year_input]
        if len(batch_years_str) == 1:
            match_stage["subject_data.academic_year"] = batch_years_str[0]
        else:
            match_stage["subject_data.academic_year"] = {"$in": batch_years_str}
            
    # Handle Semester Filter
    if semester:
        semester_input = [semester] if isinstance(semester, int) else semester
        match_stage["subject_data.semester"] = (
            semester_input[0] if len(semester_input) == 1 else {"$in": semester_input}
        )
    
    # Add match stage if any filters were provided
    if match_stage:
        pipeline.append({"$match": match_stage})

    # 4️⃣ Sort
    pipeline.append({
        "$sort": {"date": 1}
    })

    stats_docs = await SubjectSessionStats.aggregate(pipeline).to_list()
    logger.info(f"Found {len(stats_docs)} records")

    # ---------------- BUILD RESPONSE ----------------
    records = []

    for stat in stats_docs:
        records.append({
            "attendance_id": str(stat["session_id"].id),
            "date": stat["date"].date().isoformat(),
            "day": stat["date"].strftime("%A"),
            "subject": stat["subject_data"]["subject_name"],
            "semester": stat["subject_data"]["semester"],
            "teacher": stat["teacher_data"]["first_name"] + " " + stat["teacher_data"]["last_name"],
            "component": stat["subject_data"]["component"],
            "present_count": stat["present_count"],
            "absent_count": stat["absent_count"],
            "attendance_percentage": stat["percentage_present"]
        })

    return {
        "success": True,
        "message": "Attendance History Fetched Successfully",
        "records": records
    }