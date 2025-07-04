from fastapi import HTTPException
from bson import ObjectId
from datetime import datetime
from app.core.database import get_db
from app.schemas.timetable import Timetable


async def add_timetable(request, user_data: dict):
    
    # Validate user role
    if user_data["role"] != "clerk":
        raise HTTPException(
            status_code=403,
            detail="Only clerks can create timetables"
        )

    db = get_db()
    
    # Validate timetable uniqueness
    existing_timetable = await db.timetables.find_one({
        "academic_year": request.academic_year,
        "department": request.department,
        "program": request.program,
        "semester": request.semester
    })
    if existing_timetable:
        raise HTTPException(
            status_code=400,
            detail="Timetable already exists for this academic year, department, program, and semester"
        )

    # Convert request to dict and prepare for insertion
    timetable_data = request.model_dump()
    
    # Convert all subject strings to ObjectId in the schedule
    for day in timetable_data["schedule"]:
        for session in timetable_data["schedule"][day]:
            # Validate subject ID format
            if not ObjectId.is_valid(session["subject"]):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid subject ID format: {session['subject']}"
                )
            
            # Convert to ObjectId
            session["subject"] = ObjectId(session["subject"])
            
            # Validate subject exists
            subject_exists = await db.subjects.find_one({"_id": session["subject"]})
            if not subject_exists:
                raise HTTPException(
                    status_code=400,
                    detail=f"Subject with ID {session['subject']} does not exist"
                )

    # Validate no overlapping sessions
    for day, sessions in timetable_data["schedule"].items():
        if day not in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid day: {day}"
            )

        # Sort sessions by start_time to simplify overlap checking
        sorted_sessions = sorted(sessions, key=lambda s: datetime.strptime(s["start_time"], "%H:%M"))

        for i, session in enumerate(sorted_sessions):
            # Convert times to datetime for comparison
            try:
                start_time = datetime.strptime(session["start_time"], "%H:%M")
                end_time = datetime.strptime(session["end_time"], "%H:%M")
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid time format in session on {day}"
                )
            
            # Check for overlapping sessions on same day
            for j in range(i + 1, len(sorted_sessions)):
                other_session = sorted_sessions[j]
                try:
                    other_start = datetime.strptime(other_session["start_time"], "%H:%M")
                    other_end = datetime.strptime(other_session["end_time"], "%H:%M")
                except ValueError:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid time format in session on {day}"
                    )

                # Overlap condition: (start1 < end2 and end1 > start2)
                if not (end_time <= other_start or start_time >= other_end):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Overlapping sessions detected on {day}: Session from {session['start_time']}-{session['end_time']} overlaps with {other_session['start_time']}-{other_session['end_time']}"
                    )

    # Add creation timestamp
    timetable_data["created_at"] = datetime.utcnow()

    # Insert timetable into database
    result = await db.timetables.insert_one(timetable_data)

    if not result.inserted_id:
        raise HTTPException(
            status_code=500,
            detail="Failed to create timetable"
        )

    return {
        "message": "Timetable created successfully",
        "timetable_id": str(result.inserted_id)
    }