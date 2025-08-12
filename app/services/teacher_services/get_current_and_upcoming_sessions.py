from fastapi import HTTPException, status
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import List, Dict, Any
from bson import DBRef

from app.schemas.teacher import Teacher
from app.schemas.session import Session

async def get_current_and_upcoming_sessions(user_data: dict) -> Dict[str, Any]:
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
        session_list = await Session.find({
            "day": weekday_name,
            "teacher": DBRef("teachers", teacher.id),
        }).to_list()

        # Fetch linked teacher and subject data
        for session in session_list:
            await session.fetch_link("teacher")
            await session.fetch_link("subject")
    except Exception as e:
        print(f"Error fetching sessions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch session records"
        )

    # 5. Process sessions and categorize them
    upcoming = []
    current = []
    past = []
    
    for session in session_list:
        try:
            # Create timezone-aware datetime objects
            start_time = datetime.strptime(f"{today} {session.start_time}", "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo("Asia/Kolkata"))
            end_time = datetime.strptime(f"{today} {session.end_time}", "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo("Asia/Kolkata"))

            # Prepare session data with fetched subject and teacher details
            session_data = {
                "session_id": str(session.id),
                "date": str(today),
                "day": session.day,
                "start_time": session.start_time,
                "end_time": session.end_time,
                "subject_code": str(session.subject.subject_code) if session.subject and hasattr(session.subject, "subject_code") else None,
                "subject_name": session.subject.subject_name if session.subject and hasattr(session.subject, "subject_name") else None,
                "program": session.program,
                "department": session.department,
                "semester": session.semester,
                "academic_year": session.academic_year,
                "teacher_name": f"{session.teacher.first_name} {session.teacher.last_name}" if session.teacher and hasattr(session.teacher, "first_name") and hasattr(session.teacher, "last_name") else None
            }

            # Categorize session
            if start_time <= current_time <= end_time:
                current.append(session_data)
            elif start_time > current_time:
                upcoming.append(session_data)
            else:
                past.append(session_data)

        except Exception as e:
            print(f"Error processing session {session.id}: {str(e)}")
            continue

    # 6. Sort each category by start_time
    for session_list in [upcoming, current, past]:
        session_list.sort(key=lambda x: datetime.strptime(f"{x['date']} {x['start_time']}", "%Y-%m-%d %H:%M"))

    # 7. Construct final response
    return {
        "status": "success",
        "data": {
            "upcoming": upcoming,
            "current": current,
            "past": past
        }
    }