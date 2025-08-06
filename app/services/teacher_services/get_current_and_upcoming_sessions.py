from fastapi import HTTPException, status
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import List, Dict, Any
from bson import DBRef

from app.schemas.teacher import Teacher
from app.schemas.session import Session

async def get_current_and_upcoming_sessions(user_data: dict) -> List[Dict[str, Any]]:
    # 1. Check if user is a teacher
    print(f"User data: {user_data}")
    if user_data.get("role") != "teacher":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only teachers can access this endpoint"
        )

    # 2. Fetch the teacher by email
    teacher_email = user_data.get("email")
    print(f"Teacher email: {teacher_email}")
    teacher = await Teacher.find_one(Teacher.email == teacher_email)
    if not teacher:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Teacher not found"
        )

    # 3. Get current date and weekday name in IST
    current_time = datetime.now(tz=ZoneInfo("Asia/Kolkata"))
    today = current_time.date()
    weekday_name = current_time.strftime("%A")
    print(f"Current time: {current_time}, Day: {weekday_name}")

    # 4. Query sessions for today and this teacher
    try:
        # Use raw dictionary-style query with DBRef
        session_list = await Session.find({
            "day": weekday_name,
            "teacher": DBRef("teachers", teacher.id),
        }).to_list()
        print(f"Found {len(session_list)} sessions")
    except Exception as e:
        print(f"Error fetching sessions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch session records"
        )

    # 5. Process each session to determine its status
    result = []
    for session in session_list:
        try:
            # Create timezone-aware datetime objects
            start_time = datetime.strptime(f"{today} {session.start_time}", "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo("Asia/Kolkata"))
            end_time = datetime.strptime(f"{today} {session.end_time}", "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo("Asia/Kolkata"))

            status_label = (
                "current" if start_time <= current_time <= end_time
                else "upcoming" if start_time > current_time
                else "past"
            )

            result.append({
                "session_id": str(session.id),
                "date": str(today),
                "day": session.day,
                "start_time": session.start_time,
                "end_time": session.end_time,
                "subject_code": str(session.subject.subject_code) if hasattr(session.subject, "subject_code") else None,
                "subject_name": session.subject.subject_name if hasattr(session.subject, "subject_name") else None,
                "program": session.program,
                "department": session.department,
                "semester": session.semester,
                "academic_year": session.academic_year,
                "status": status_label
            })

        except Exception as e:
            print(f"Error processing session {session.id}: {str(e)}")
            continue

    # 6. Sort result by start_time
    result.sort(key=lambda x: datetime.strptime(f"{x['date']} {x['start_time']}", "%Y-%m-%d %H:%M"))

    return result