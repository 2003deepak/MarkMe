from fastapi import HTTPException
from beanie import Link
from bson import ObjectId , DBRef
from datetime import datetime
from app.schemas.timetable import Timetable, Session
from app.schemas.subject import Subject
from app.models.allModel import TimetableRequest
import logging

async def add_timetable(request: TimetableRequest, user_data: dict):
    # Validate user role
    if user_data["role"] != "clerk":
        raise HTTPException(
            status_code=403,
            detail="Only clerks can create timetables"
        )

    # Validate timetable uniqueness
    existing_timetable = await Timetable.find_one(
        Timetable.academic_year == request.academic_year,
        Timetable.department == request.department,
        Timetable.program == request.program,
        Timetable.semester == request.semester
    )
    if existing_timetable:
        raise HTTPException(
            status_code=400,
            detail="Timetable already exists for this academic year, department, program, and semester"
        )

    # Collect all subject IDs from the request
    subject_ids = set()
    for day, sessions in request.schedule.items():
        for session in sessions:
            subject_ids.add(session.subject)

    # Validate that all subjects exist
    from app.schemas.subject import Subject
    subjects = await Subject.find({"_id": {"$in": [ObjectId(sid) for sid in subject_ids]}}).to_list()
    if len(subjects) != len(subject_ids):
        missing_ids = subject_ids - {str(subject.id) for subject in subjects}
        raise HTTPException(status_code=400, detail=f"Invalid subject IDs: {missing_ids}")

    # Convert SessionRequest to Session
    schedule = {}
    for day, sessions in request.schedule.items():
        if day not in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]:
            raise HTTPException(status_code=400, detail=f"Invalid day: {day}")
        
        schedule[day] = [
            Session(
                start_time=session.start_time,
                end_time=session.end_time,
                subject=DBRef(collection="subject", id=ObjectId(session.subject))
            )
            for session in sessions
        ]

    # Validate no overlapping sessions
    for day, sessions in schedule.items():
        sorted_sessions = sorted(sessions, key=lambda s: datetime.strptime(s.start_time, "%H:%M"))
        
        for i, session in enumerate(sorted_sessions):
            try:
                start_time = datetime.strptime(session.start_time, "%H:%M")
                end_time = datetime.strptime(session.end_time, "%H:%M")
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid time format in session on {day}"
                )
            
            for j in range(i + 1, len(sorted_sessions)):
                other_session = sorted_sessions[j]
                try:
                    other_start = datetime.strptime(other_session.start_time, "%H:%M")
                    other_end = datetime.strptime(other_session.end_time, "%H:%M")
                except ValueError:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid time format in session on {day}"
                    )

                if not (end_time <= other_start or start_time >= other_end):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Overlapping sessions detected on {day}: Session from {session.start_time}-{session.end_time} overlaps with {other_session.start_time}-{other_session.end_time}"
                    )

    # Create Timetable document
    timetable_data = Timetable(
        academic_year=request.academic_year,
        department=request.department,
        program=request.program,
        semester=request.semester,
        schedule=schedule
    )

    try:
        await timetable_data.insert()
        return {
            "message": "Timetable created successfully",
            "timetable_id": str(timetable_data.id)
        }
    except Exception as e:
        logging.error(f"Error creating timetable: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create timetable")