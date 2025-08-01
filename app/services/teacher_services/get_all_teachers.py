from fastapi import HTTPException
from pydantic import BaseModel, EmailStr, HttpUrl
from typing import List, Optional
from app.core.redis import redis_client
import json
from app.schemas.clerk import Clerk
from app.schemas.teacher import Teacher
from app.schemas.subject import Subject
from app.models.allModel import TeacherShortView, SubjectOutputDetail

async def get_all_teachers(user_data):
    if user_data["role"] != "clerk":
        raise HTTPException(status_code=403, detail="Only clerks can access this route")

    email = user_data["email"]

    # Get clerk to filter department
    clerk = await Clerk.find_one(Clerk.email == email)
    if clerk is None or not clerk.department:
        raise HTTPException(status_code=400, detail="Clerk department not found")

    department = clerk.department
    cache_key = f"teachers:{department}"

    # Check cache
    cached_teachers = await redis_client.get(cache_key)
    if cached_teachers:
        return {"status": "success", "data": json.loads(cached_teachers)}

    # Get teachers with linked subjects
    teachers = await Teacher.find(
        Teacher.department == department,
        fetch_links=True
    ).to_list()

    teachers_data = []
    for t in teachers:
        # Convert linked subjects to SubjectOutputDetail
        subjects_assigned = [
            SubjectOutputDetail(
                subject_code=subject.subject_code,
                subject_name=subject.subject_name,
                component=subject.component
            ) for subject in t.subjects_assigned
        ]

        # Create TeacherShortView instance for validation
        teacher_view = TeacherShortView(
            teacher_id=t.teacher_id,
            first_name=t.first_name,
            middle_name=t.middle_name,
            last_name=t.last_name,
            email=t.email,
            mobile_number=t.mobile_number,
            department=t.department,
            profile_picture=t.profile_picture,
            profile_picture_id=t.profile_picture_id,
            subjects_assigned=subjects_assigned
        )

        # Convert to dict, ensuring HttpUrl is handled
        teacher_dict = teacher_view.dict()
        # Explicitly convert profile_picture to string if it exists
        if teacher_dict["profile_picture"]:
            teacher_dict["profile_picture"] = str(teacher_dict["profile_picture"])
        teachers_data.append(teacher_dict)

    # Serialize to JSON and cache
    await redis_client.setex(cache_key, 3600, json.dumps(teachers_data))
    return {"status": "success", "data": teachers_data}