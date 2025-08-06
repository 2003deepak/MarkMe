from app.models.allModel import TimeTableRequest
from app.schemas.session import Session
from app.schemas.subject import Subject
from app.schemas.teacher import Teacher
from fastapi import HTTPException
from typing import Dict, List
from beanie.odm.fields import PydanticObjectId
import traceback

async def add_timetable(request: TimeTableRequest, user_data: dict) -> dict:
    try:
        # Validate request fields
        if not all([request.academic_year, request.department, request.program, request.semester]):
            return {
                'status': 'fail',
                'message': 'Missing required fields: academic_year, department, program, or semester'
            }

        if not request.schedule or not isinstance(request.schedule, dict):
            return {
                'status': 'fail',
                'message': 'Invalid or empty schedule provided'
            }


        for day, entries in request.schedule.items():
            # Skip days with no entries (e.g., weekends)
            if not entries:
                continue

            session_links: List[PydanticObjectId] = []

            for entry in entries:
                # Validate entry fields
                if not all([entry.subject, entry.start_time, entry.end_time]):
                    return {
                        'status': 'fail',
                        'message': 'Invalid entry: missing subject, start_time, or end_time'
                    }

                # Fetch Subject
                try:
                    subject = await Subject.get(entry.subject)
                    if not subject:
                        return {
                            'status': 'fail',
                            'message': f'Subject {entry.subject} not found'
                        }
                except Exception as e:
                    return {
                        'status': 'fail',
                        'message': f'Error fetching subject {entry.subject}: {str(e)}'
                    }

                # Check if teacher is assigned
                if not subject.teacher_assigned:
                    return {
                        'status': 'fail',
                        'message': f'No teacher assigned to subject {subject.subject_name}'
                    }

                # Resolve Teacher
                try:
                    teacher_doc = await subject.teacher_assigned.fetch()
                    if not teacher_doc:
                        return {
                            'status': 'fail',
                            'message': f'Teacher not found for subject {subject.subject_name}'
                        }
                except Exception as e:
                    return {
                        'status': 'fail',
                        'message': f'Error fetching teacher for subject {subject.subject_name}: {str(e)}'
                    }

                # Validate time
                if entry.start_time >= entry.end_time:
                    return {
                        'status': 'fail',
                        'message': f'Invalid time range: start_time {entry.start_time} must be before end_time {entry.end_time}'
                    }

                # Create and insert Session
                session = Session(
                    day=day,
                    start_time=entry.start_time,
                    end_time=entry.end_time,
                    subject=subject,
                    teacher=teacher_doc,
                    academic_year=request.academic_year,
                    department=request.department,
                    program=request.program,
                    semester=request.semester
                )

                try:
                    await session.insert()
                    if not session.id:
                        return {
                            'status': 'fail',
                            'message': 'Failed to generate session ID'
                        }
                    session_links.append(session.id)
                except Exception as e:
                    return {
                        'status': 'fail',
                        'message': f'Error inserting session for subject {subject.subject_name}: {str(e)}'
                    }

        

        return {
            'status': 'success',
            'message': 'Timetable created successfully',
        }

    except Exception as e:
        # Catch any unexpected errors
        return {
            'status': 'fail',
            'message': f'Unexpected error occurred: {str(e)}'
        }