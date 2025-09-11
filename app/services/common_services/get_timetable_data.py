from typing import List, Optional
from fastapi import HTTPException
from app.schemas.session import Session
from app.models.allModel import TimeTableResponse, SessionShortView, DaySchedule
from app.core.redis import redis_client
import json
import logging
from datetime import datetime


async def get_timetable_data(department: str, program: str, semester: str, academic_year: str, user_data: dict) -> TimeTableResponse:
<<<<<<< HEAD
    
=======
>>>>>>> 88aa3ea43198ec465a43e1cc5393a6cf37a25d5d
    print(
        f"Starting get_timetable_data with department={department}, program={program}, semester={semester}, academic_year={academic_year}")

    if user_data.get("role") not in ["teacher", "admin", "clerk", "student"]:
        print(f"Unauthorized access attempt by role: {user_data.get('role')}")
        raise HTTPException(
            status_code=403,
            detail={"status": "fail",
                    "message": "User must be a teacher, admin, clerk, or student"}
        )

    try:
        if not department.strip() or not program.strip():
            print("Invalid department or program")
            raise HTTPException(
                status_code=400,
                detail={"status": "fail",
                        "message": "Department and program cannot be empty"}
            )
        try:
            semester_int = int(semester)
            if not (1 <= semester_int <= 8):
                raise ValueError
        except ValueError:
            print(f"Invalid semester: {semester}")
            raise HTTPException(
                status_code=400,
                detail={"status": "fail",
                        "message": "Semester must be a number between 1 and 8"}
            )
        try:
            academic_year_int = int(academic_year)
            current_year = datetime.utcnow().year
            if not (2000 <= academic_year_int <= current_year + 1):
                raise ValueError
        except ValueError:
            print(f"Invalid academic_year: {academic_year}")
            raise HTTPException(
                status_code=400,
                detail={
                    "status": "fail", "message": f"Academic year must be between 2000 and {current_year + 1}"}
            )

        cache_key = f"timetable:{program}:{department}:{semester}:{academic_year}"
        print(f"Checking cache with key: {cache_key}")

        cached_data = await redis_client.get(cache_key)
        if cached_data:
            print("Cache hit: Returning cached timetable data")
            return TimeTableResponse.model_validate_json(cached_data)

        query = {
            "department": department,
            "program": program,
            "semester": semester,
            "academic_year": academic_year
        }
        print(f"Querying sessions with filter: {query}")

        sessions = await Session.find(query).sort("start_time").to_list()
        if not sessions:
            print("No sessions found for query")
            return TimeTableResponse(
                program=program,
                department=department,
                semester=semester,
                academic_year=academic_year,
                schedule=[]
            )

        # Fetch linked subject and teacher data
        for session in sessions:
            if session.subject:
                session.subject = await session.subject.fetch()
            if session.teacher:
                session.teacher = await session.teacher.fetch()
        print("Fetched linked subject and teacher data")

        day_sessions = {}
        days_order = ["Monday", "Tuesday", "Wednesday",
                      "Thursday", "Friday", "Saturday", "Sunday"]
        for session in sessions:
            day = session.day
            if day not in day_sessions:
                day_sessions[day] = []
            teacher_name = f"{session.teacher.first_name} {session.teacher.middle_name or ''} {session.teacher.last_name}".strip()
            session_view = SessionShortView(
                session_id=str(session.id),
                start_time=session.start_time,
                end_time=session.end_time,
                subject_name=session.subject.subject_name,
                teacher_name=teacher_name
            )
            day_sessions[day].append(session_view)

        schedule = [
            # Changed from sessions to day_sessions[day]
            DaySchedule(day=day, sessions=day_sessions[day])
            for day in days_order
            if day in day_sessions
        ]

        response = TimeTableResponse(
            program=program,
            department=department,
            semester=semester,
            academic_year=academic_year,
            schedule=schedule
        )

        try:
            await redis_client.setex(
                name=cache_key,
                time=3600,
                value=response.model_dump_json()
            )
            print(f"Cached timetable data with key: {cache_key}")
        except Exception as e:
            print(f"Failed to cache timetable data: {str(e)}")

        return response

    except HTTPException:
        print("HTTPException raised during get_timetable_data")
        raise

    except Exception as e:
        print(f"Unhandled exception during get_timetable_data: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail={"status": "fail",
                    "message": f"Error fetching timetable: {str(e)}"}
        )
