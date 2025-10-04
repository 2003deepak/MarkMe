from fastapi import HTTPException, status, Request
from fastapi.responses import JSONResponse
from typing import Dict, Any
from bson import DBRef, ObjectId
from app.schemas.teacher import Teacher
from app.schemas.session import Session
from app.schemas.student import Student
from app.models.allModel import StudentShortView
from app.core.redis import redis_client
import json

async def fetch_class(request: Request, batch_year: int, program: str, semester: int):
    
    user_role = request.state.user.get("role")
    if user_role not in {"teacher", "clerk"}:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "status": "fail",
                "message": "Access denied. Only teachers and clerks can use this endpoint."
            }
        )

    # Normalize input values
    department = request.state.user.get("department")
    program = program.upper()
    
    # Create cache key
    cache_key = f"students:{program}:{department}:{semester}:{batch_year}"
    
    print(f"Cache key: {cache_key}")
    
    try:
        # Check redis_client cache first
        cached_data = await redis_client.get(cache_key)
        if cached_data:
            print(f"Cache hit for {cache_key}")
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=json.loads(cached_data)
            )

        # Cache miss - fetch from database
        students = await Student.find(
            {
                "program": program,
                "department": department,
                "semester": semester,
                "batch_year": batch_year
            }
        ).project(StudentShortView).to_list()

        print(f"Found {len(students)} students")

        student_list = [
            {
                "student_id": student.student_id,
                "name": f"{student.first_name} {student.middle_name or ''} {student.last_name}".strip() if student.first_name and student.last_name else None,
                "roll_number": student.roll_number,
                "email": student.email,
                "phone": student.phone,
                "department": student.department,
                "program": student.program,
                "semester": student.semester,
                "batch_year": student.batch_year,
                "profile_picture": str(student.profile_picture) if student.profile_picture else None,
                "is_verified": student.is_verified
            }
            for student in students
        ]

        response = {
            "status": "success",
            "data": student_list
        }

        # Store in redis_client with 1-hour expiration
        await redis_client.setex(
            cache_key,
            3600,  # Cache for 1 hour
            json.dumps(response)
        )
        print(f"Cached data for {cache_key}")

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response
        )

    except Exception as e:
        print(f"Error fetching students: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "status": "fail",
                "message": "Failed to fetch student records"
            }
        )