from app.models.allModel import TimeTableRequest
from app.schemas.session import Session
from app.schemas.subject import Subject
from app.schemas.teacher import Teacher
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from typing import Dict, List
from beanie.odm.fields import PydanticObjectId
import traceback

async def add_timetable(request: Request, request_model: TimeTableRequest) -> dict:
    try:
        # Get department from request state user
        department = request.state.user.get("department")
        if not department:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    'message': 'Department not found in user information'
                }
            )

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
                    department=department,  # Use department from request state
                    program=request_model.program,
                    semester=request_model.semester
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