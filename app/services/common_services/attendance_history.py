from datetime import datetime
from fastapi import Request
from fastapi.responses import JSONResponse
from app.schemas.attendance import Attendance
import logging

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


async def student_attendance_history(request: Request, month: int, year: int):
    logger.info("STUDENT ATTENDANCE HISTORY API CALLED")
    logger.info(f"Params → month={month}, year={year}")

    user = request.state.user
    logger.info(f"User → {user.get('email')} | Roll: {user.get('roll_no')} | Role: {user.get('role')}")

    if user.get("role") != "student":
        return JSONResponse(status_code=401, content={"success": False, "message": "Access denied"})

    roll_no = user.get("roll_no")
    if not roll_no:
        return JSONResponse(status_code=400, content={"success": False, "message": "Roll number missing"})

    program = user["program"]
    department = user["department"]
    semester = str(user["semester"])
    batch_year = str(user["batch_year"])
    bit_index = roll_no - 1

    logger.info(f"Student → Roll {roll_no} | Program={program}, Dept={department}, Sem={semester}, Year={batch_year}")

    # Date range
    start_date = datetime(year, month, 1)
    end_date = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)

    logger.info(f"Date range → {start_date.date()} to {end_date.date()}")

    # -------------------------
    # AGGREGATION PIPELINE
    # -------------------------
    pipeline = [
        {"$match": {"date": {"$gte": start_date, "$lt": end_date}}},

        # Join → Session
        {
            "$lookup": {
                "from": "sessions",
                "localField": "session.$id",
                "foreignField": "_id",
                "as": "session_data"
            }
        },
        {"$unwind": {"path": "$session_data", "preserveNullAndEmptyArrays": True}},

        # Filter by student eligibility
        {
            "$match": {
                "session_data.program": program,
                "session_data.department": department,
                "session_data.semester": semester,
                "session_data.academic_year": batch_year
            }
        },

        # Join → Subject
        {
            "$lookup": {
                "from": "subjects",
                "localField": "session_data.subject.$id",
                "foreignField": "_id",
                "as": "subject_data"
            }
        },
        {"$unwind": {"path": "$subject_data", "preserveNullAndEmptyArrays": True}},


        {"$sort": {"date": 1}}
    ]

    logger.info("Executing aggregation pipeline...")
    attendances = await Attendance.aggregate(pipeline).to_list()
    logger.info(f"Found {len(attendances)} records")

    # -------------------------
    # BUILD FINAL RESPONSE
    # -------------------------
    records = []

    for a in attendances:
        session = a.get("session_data")
        subject = a.get("subject_data")

        subject_name = subject.get("subject_name") if subject else "Unknown Subject"

        students_str = a.get("students", "")
        present = len(students_str) > bit_index and students_str[bit_index] == "1"
        
        # ✅ extract session timings
        start_time = session.get("start_time") if session else None
        end_time = session.get("end_time") if session else None

        records.append({
            "attendance_id": str(a["_id"]),
            "date": a["date"].date().isoformat(),
            "day": a["date"].strftime("%A"),
            "subject": subject_name,
            "start_time": start_time,
            "end_time": end_time,
            "present": present
        })

    total = len(records)
    present_count = sum(1 for r in records if r["present"])
    percentage = round((present_count / total) * 100, 2) if total else 0

    logger.info(f"FINAL → total={total}, present={present_count}, percent={percentage}%")

    return {
        "success": True,
        "message" : "Attendance History Fetched Successfully",
        "records": records
    }
