import datetime

from app.models.allModel import TimeTableRequest, UpdateTimeTableRequest
from app.schemas.session import Session
from app.schemas.subject import Subject
from app.schemas.teacher import Teacher
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from typing import Dict, List
from beanie.odm.fields import PydanticObjectId
from app.utils.redis_key_deletion import invalidate_redis_keys

async def add_timetable(request: Request, request_model: TimeTableRequest) -> dict:
    try:
        

        # Validate request fields
        if not all([request_model.academic_year, request_model.program, request_model.semester]):
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    'message': 'Missing required fields: academic_year, program, or semester'
                }
            )

        if not request_model.schedule or not isinstance(request_model.schedule, dict):
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    'message': 'Invalid or empty schedule provided'
                }
            )

        for day, entries in request_model.schedule.items():
            # Skip days with no entries (e.g., weekends)
            if not entries:
                continue

            session_links: List[PydanticObjectId] = []

            for entry in entries:
                # Validate entry fields
                if not all([entry.subject, entry.start_time, entry.end_time]):
                    return JSONResponse(
                        status_code=400,
                        content={
                            "success": False,
                            'message': 'Invalid entry: missing subject, start_time, or end_time'
                        }
                    )

                # Fetch Subject
                try:
                    subject = await Subject.get(entry.subject)
                    if not subject:
                        return JSONResponse(
                            status_code=404,
                            content={
                                "success": False,
                                'message': f'Subject {entry.subject} not found'
                            }
                        )
                except Exception as e:
                    return JSONResponse(
                        status_code=500,
                        content={
                            "success": False,
                            'message': f'Error fetching subject {entry.subject}: {str(e)}'
                        }
                    )

                # Check if teacher is assigned
                if not subject.teacher_assigned:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "success": False,
                            'message': f'No teacher assigned to subject {subject.subject_name}'
                        }
                    )

                # Resolve Teacher
                try:
                    teacher_doc = await subject.teacher_assigned.fetch()
                    if not teacher_doc:
                        return JSONResponse(
                            status_code=404,
                            content={
                                "success": False,
                                'message': f'Teacher not found for subject {subject.subject_name}'
                            }
                        )
                except Exception as e:
                    return JSONResponse(
                        status_code=500,
                        content={
                            "success": False,
                            'message': f'Error fetching teacher for subject {subject.subject_name}: {str(e)}'
                        }
                    )

                # Validate time
                if entry.start_time >= entry.end_time:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "success": False,
                            'message': f'Invalid time range: start_time {entry.start_time} must be before end_time {entry.end_time}'
                        }
                    )

                # Create and insert Session
                session = Session(
                    day=day,
                    start_time=entry.start_time,
                    end_time=entry.end_time,
                    subject=subject,
                    teacher=teacher_doc,
                    academic_year=request_model.academic_year,
                    department=request_model.department, 
                    program=request_model.program,
                    semester=request_model.semester,
                    is_active=True
                )

                try:
                    await session.insert()
                    if not session.id:
                        return JSONResponse(
                            status_code=500,
                            content={
                                "success": False,
                                'message': 'Failed to generate session ID'
                            }
                        )
                    session_links.append(session.id)
                except Exception as e:
                    return JSONResponse(
                        status_code=500,
                        content={
                            "success": False,
                            'message': f'Error inserting session for subject {subject.subject_name}: {str(e)}'
                        }
                    )
                    
        await invalidate_redis_keys("timetable:*")

        return JSONResponse(
            status_code=201,
            content={
                'success': True,
                'message': 'Timetable created successfully',
            }
        )

    except Exception as e:
        # Catch any unexpected errors
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                'message': f'Unexpected error occurred: {str(e)}'
            }
        )


async def update_timetable(request: Request, request_model: UpdateTimeTableRequest) -> dict:
    
    try:
        
        if request.state.user.get("role") != "clerk":
            return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "message": "Unauthorized: Only clerks can update the timetable"
                }
            )

        updates = request_model.updates or []
        adds = request_model.adds or []
        deletes = request_model.deletes or []

        # ------------------ DELETE ------------------
        for session_id in deletes:
            session = await Session.get(session_id)
            if session:
                session.is_active = False
                session.deleted_by = request.state.user.id
                session.updated_at = datetime.utcnow()
                await session.save()

        # ------------------ UPDATE ------------------
        for item in updates:

            old_session = await Session.get(item.session_id)

            if not old_session:
                return JSONResponse(
                    status_code=404,
                    content={
                        "success": False,
                        "message": f"Session {item.session_id} not found"
                    }
                )

            subject = await Subject.get(item.subject)
            if not subject:
                return JSONResponse(
                    status_code=404,
                    content={
                        "success": False,
                        "message": "Subject not found"
                    }
                )

            if not subject.teacher_assigned:
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "message": f"No teacher assigned to subject {subject.subject_name}"
                    }
                )

            teacher_doc = await subject.teacher_assigned.fetch()

            if item.start_time >= item.end_time:
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "message": "Invalid time range"
                    }
                )

            # deactivate old
            old_session.is_active = False
            old_session.deleted_by = request.state.user.id
            old_session.updated_at = datetime.utcnow()

            # create new
            new_session = Session(
                day=item.day or old_session.day,
                start_time=item.start_time,
                end_time=item.end_time,
                subject=subject,
                teacher=teacher_doc,
                academic_year=item.academic_year or old_session.academic_year,
                department=item.department or old_session.department,
                program=item.program or old_session.program,
                semester=item.semester or old_session.semester,
                is_active=True,
                deleted_by=request.state.user.get("id")
            )

            await new_session.insert()
            await old_session.save()

        # ------------------ ADD ------------------
        for item in adds:

            subject = await Subject.get(item.subject)
            if not subject:
                return JSONResponse(
                    status_code=404,
                    content={
                        "success": False,
                        "message": "Subject not found"
                    }
                )

            if not subject.teacher_assigned:
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "message": f"No teacher assigned to subject {subject.subject_name}"
                    }
                )

            teacher_doc = await subject.teacher_assigned.fetch()

            if item.start_time >= item.end_time:
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "message": "Invalid time range"
                    }
                )

            new_session = Session(
                day=item.day,
                start_time=item.start_time,
                end_time=item.end_time,
                subject=subject,
                teacher=teacher_doc,
                academic_year=item.academic_year,
                department=item.department,
                program=item.program,
                semester=item.semester,
                is_active=True,
                deleted_by=request.state.user.get("id")
            )

            await new_session.insert()

        await invalidate_redis_keys("timetable:*")

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Timetable updated successfully"
            }
        )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"Unexpected error: {str(e)}"
            }
        )