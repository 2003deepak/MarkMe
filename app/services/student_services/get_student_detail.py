from fastapi import HTTPException
from pydantic import BaseModel, EmailStr, HttpUrl
from typing import List, Optional
from app.core.redis import redis_client
import json
from app.schemas.student import Student
from app.schemas.subject import Subject
from app.schemas.teacher import Teacher
from app.models.allModel import StudentShortView, SubjectOutputDetail
from bson import ObjectId
from datetime import datetime
from beanie.operators import In
import logging

# JSON encoder to handle ObjectId and datetime
class MongoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, HttpUrl):
            return str(obj)  # Convert HttpUrl to string
        return super().default(obj)

async def get_student_detail(user_data: dict):
    user_email = user_data["email"]
    user_role = user_data["role"]

    if user_role != "student":
        logging.info(f"Unauthorized access attempt by role: {user_role}")
        raise HTTPException(
            status_code=403,
            detail={"status": "fail", "message": "Only students can access this route"}
        )

    cache_key_student = f"student:{user_email}"
    cached_student = await redis_client.get(cache_key_student)

    if cached_student:
        logging.info(f"Student data for {user_email} retrieved from cache.")
        student_data = json.loads(cached_student)
        try:
            validated_student_data = StudentShortView.model_validate(student_data)
            return {"status": "success", "data": validated_student_data.model_dump(exclude_none=True)}
        except Exception as e:
            logging.warning(f"Cached student data for {user_email} is invalid: {e}. Refetching.")

    student = await Student.find_one(Student.email == user_email)
    if not student:
        logging.error(f"Student with email {user_email} not found.")
        raise HTTPException(
            status_code=404,
            detail={"status": "fail", "message": "Student not found"}
        )

    program = student.program
    department = student.department
    semester = student.semester

    if not all([program, department, semester]):
        logging.error(f"Student {user_email} missing essential details: program={program}, department={department}, semester={semester}")
        raise HTTPException(
            status_code=400,
            detail={"status": "fail", "message": "Student missing program, department, or semester"}
        )

    cache_key_subjects = f"subjects:{program}:{department}:{semester}"
    cached_subjects = await redis_client.get(cache_key_subjects)

    subjects_data_for_pydantic = []
    subjects_data_for_caching = []

    if cached_subjects:
        logging.info(f"Subjects data for {program}-{department}-{semester} retrieved from cache.")
        raw_cached_subjects = json.loads(cached_subjects)
        for subj in raw_cached_subjects:
            pydantic_subject = {
                "subject_code": subj["subject_code"],
                "subject_name": subj["subject_name"],
                "department": subj["department"],
                "semester": subj["semester"],
                "program": subj["program"],
                "component": subj.get("component", ""),
                "credit": subj["credit"],
                "teacher_assigned": None  # Default to None if no teacher_assigned
            }
            if subj.get("teacher_assigned"):
                try:
                    teacher_id = ObjectId(subj["teacher_assigned"])
                    teacher = await Teacher.find_one(Teacher.id == teacher_id, fetch_links=True)
                    if teacher:
                        pydantic_subject["teacher_assigned"] = {
                            "teacher_id": str(teacher.id),
                            "first_name": teacher.first_name,
                            "middle_name": teacher.middle_name,
                            "last_name": teacher.last_name,
                            "email": teacher.email,
                            "mobile_number": teacher.mobile_number,
                            "department": teacher.department,
                            "profile_picture": teacher.profile_picture,
                            "profile_picture_id": teacher.profile_picture_id
                        }
                except Exception as e:
                    logging.warning(f"Failed to convert cached teacher_assigned '{subj['teacher_assigned']}' to ObjectId: {e}")
                    pydantic_subject["teacher_assigned"] = None
            subjects_data_for_pydantic.append(pydantic_subject)
            subjects_data_for_caching.append({
                **pydantic_subject,
                "teacher_assigned": str(pydantic_subject["teacher_assigned"]) if pydantic_subject["teacher_assigned"] else None
            })
    else:
        logging.info(f"Fetching subjects data for {program}-{department}-{semester} from database.")
        subjects = await Subject.find(
            In(Subject.program, [program]),
            In(Subject.department, [department]),
            In(Subject.semester, [semester]),
            fetch_links=True
        ).to_list()

        for subject in subjects:
            teacher_obj = subject.teacher_assigned
            teacher_data = None
            if teacher_obj:
                teacher_data = {
                    "teacher_id": str(teacher_obj.id),
                    "first_name": teacher_obj.first_name,
                    "middle_name": teacher_obj.middle_name,
                    "last_name": teacher_obj.last_name,
                    "email": teacher_obj.email,
                    "mobile_number": teacher_obj.mobile_number,
                    "department": teacher_obj.department,
                    "profile_picture": teacher_obj.profile_picture,
                    "profile_picture_id": teacher_obj.profile_picture_id
                }
            subjects_data_for_pydantic.append({
                "subject_code": subject.subject_code,
                "subject_name": subject.subject_name,
                "department": subject.department,
                "semester": subject.semester,
                "program": subject.program,
                "component": subject.component or "",
                "credit": subject.credit,
                "teacher_assigned": teacher_data
            })
            subjects_data_for_caching.append({
                "subject_code": subject.subject_code,
                "subject_name": subject.subject_name,
                "department": subject.department,
                "semester": subject.semester,
                "program": subject.program,
                "component": subject.component or "",
                "credit": subject.credit,
                "teacher_assigned": str(teacher_data["teacher_id"]) if teacher_data else None
            })

        await redis_client.setex(
            cache_key_subjects,
            3600,
            json.dumps(subjects_data_for_caching, cls=MongoJSONEncoder)
        )
        logging.info(f"Subjects data for {program}-{department}-{semester} cached.")

    student_dict = {
        "student_id": student.student_id,
        "first_name": student.first_name,
        "middle_name": student.middle_name,
        "last_name": student.last_name,
        "email": student.email,
        "phone": student.phone,
        "department": student.department,
        "program": student.program,
        "semester": student.semester,
        "batch_year": student.batch_year,
        "roll_number": student.roll_number,
        "profile_picture": student.profile_picture,
        "profile_picture_id": student.profile_picture_id,
        "subjects_assigned": subjects_data_for_pydantic
    }

    try:
        student_out_data = StudentShortView.model_validate(student_dict)
        student_dict_for_response = student_out_data.model_dump(
            exclude_none=True,
            mode="json"
        )
    except Exception as e:
        logging.error(f"Pydantic validation error for student {user_email}: {e}")
        raise HTTPException(
            status_code=500,
            detail={"status": "fail", "message": f"Data validation error: {e}"}
        )

    await redis_client.setex(
        cache_key_student,
        3600,
        json.dumps(student_dict_for_response, cls=MongoJSONEncoder)
    )
    logging.info(f"Combined student and subjects data for {user_email} cached.")

    return {"status": "success", "data": student_dict_for_response}