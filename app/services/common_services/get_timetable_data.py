from typing import List, Optional
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from app.schemas.session import Session
from app.models.allModel import TimeTableResponse, SessionShortView, DaySchedule
from app.core.redis import redis_client
import json
import logging
from datetime import datetime


async def get_timetable_data(request: Request, department: str, program: str, semester: str, academic_year: str) -> JSONResponse:
    print(
        f"Starting get_timetable_data with department={department}, program={program}, semester={semester}, academic_year={academic_year}")

    user_role = request.state.user.get("role")
    if user_role not in ["teacher", "admin", "clerk", "student"]:
        print(f"Unauthorized access attempt by role: {user_role}")
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "message": "User must be a teacher, admin, clerk, or student"
            }
        )

    try:
        if not department.strip() or not program.strip():
            print("Invalid department or program")
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "message": "Department and program cannot be empty"
                }
            )
        try:
            semester_int = int(semester)
            if not (1 <= semester_int <= 8):
                raise ValueError
        except ValueError:
            print(f"Invalid semester: {semester}")
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "message": "Semester must be a number between 1 and 8"
                }
            )
        try:
            academic_year_int = int(academic_year)
            current_year = datetime.utcnow().year
            if not (2000 <= academic_year_int <= current_year + 1):
                raise ValueError
        except ValueError:
            print(f"Invalid academic_year: {academic_year}")
            return JSONResponse(
                status_code=400,
                content={
                    "success": False, 
                    "message": f"Academic year must be between 2000 and {current_year + 1}"
                }
            )

        cache_key = f"timetable:{program}:{department}:{semester}:{academic_year}"
        print(f"Checking cache with key: {cache_key}")

        cached_data = await redis_client.get(cache_key)
        if cached_data:
            print("Cache hit: Returning cached timetable data")
            cached_response = json.loads(cached_data)
            return JSONResponse(
                status_code=200,
                content={
                    "success" : True,
                    "message" : "Attendance Records fetched successfully",
                    "data" : cached_response
                }
            )

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
            response_data = {
                "program": program,
                "department": department,
                "semester": semester,
                "academic_year": academic_year,
                "schedule": []
            }
            return JSONResponse(
                status_code=200,
                content=response_data
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
            DaySchedule(day=day, sessions=day_sessions[day])
            for day in days_order
            if day in day_sessions
        ]

        response_data = {
            "program": program,
            "department": department,
            "semester": semester,
            "academic_year": academic_year,
            "schedule": [day_schedule.dict() for day_schedule in schedule]
        }

        try:
            await redis_client.setex(
                name=cache_key,
                time=3600,
                value=json.dumps(response_data)
            )
            print(f"Cached timetable data with key: {cache_key}")
        except Exception as e:
            print(f"Failed to cache timetable data: {str(e)}")

        return JSONResponse(
            status_code=200,
            content={
                    "success" : True,
                    "message" : "Attendance Records fetched successfully",
                    "data" : response_data
                }
            
        )

    except Exception as e:
        print(f"Unhandled exception during get_timetable_data: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"Error fetching timetable: {str(e)}"
            }
        )