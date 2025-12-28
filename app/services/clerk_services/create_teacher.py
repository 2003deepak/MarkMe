from fastapi.responses import JSONResponse
from passlib.context import CryptContext
import random
from bson import ObjectId

from app.schemas.teacher import Teacher
from app.schemas.subject import Subject
from app.utils.publisher import send_to_queue
from app.core.redis import redis_client
from app.utils.security import get_password_hash

from beanie.operators import In
from pydantic import ValidationError

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def create_teacher(request, request_model):


    # STEP 1 — AUTHORIZATION
    user_role = request.state.user.get("role")
    if user_role != "clerk":
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "message": "You don't have the right to create a teacher"
            }
        )

    try:
        
        # STEP 2 — CHECK DUPLICATE TEACHER
        
        if await Teacher.find_one(Teacher.email == request_model.email):
            return JSONResponse(
                status_code=409,
                content={
                    "success": False,
                    "message": "Teacher already exists"
                }
            )

        
        # STEP 3 — FETCH SUBJECTS USING SUBJECT _id
        
        subjects_to_assign_to_teacher = []

        if request_model.subjects_assigned:
            try:
                subject_object_ids = [
                    ObjectId(sub_id) for sub_id in request_model.subjects_assigned
                ]
            except Exception:
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "message": "Invalid subject ID format"
                    }
                )

            existing_subjects_docs = await Subject.find(
                In(Subject.id, subject_object_ids)
            ).to_list()

            # Validate invalid / missing IDs
            if len(existing_subjects_docs) != len(subject_object_ids):
                found_ids = {str(sub.id) for sub in existing_subjects_docs}
                invalid_ids = set(request_model.subjects_assigned) - found_ids

                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "message": f"Invalid subject IDs: {', '.join(invalid_ids)}"
                    }
                )

            
            # STEP 3.5 — PREVENT REASSIGNMENT (USER-FRIENDLY MESSAGE)
            
            assigned_teacher_names = set()

            for subj in existing_subjects_docs:

                subject_fresh = await Subject.find_one(
                    Subject.id == subj.id,
                    Subject.teacher_assigned != None,
                    fetch_links=True
                )

                if subject_fresh and subject_fresh.teacher_assigned:
                    teacher = subject_fresh.teacher_assigned
                    full_name = f"{teacher.first_name} {teacher.last_name}".strip()
                    assigned_teacher_names.add(full_name)

            if assigned_teacher_names:
                teacher_list = ", ".join(sorted(assigned_teacher_names))

                return JSONResponse(
                    status_code=409,
                    content={
                        "success": False,
                        "message": (
                            f"The selected subjects are already assigned to the following "
                            f"teacher(s): {teacher_list}. "
                            f"If you still want to reassign these subjects, "
                            f"please contact the Admin Department."
                        )
                    }
                )

            subjects_to_assign_to_teacher = existing_subjects_docs


        
        # STEP 4 — GENERATE UNIQUE TEACHER ID
        
        while True:
            teacher_id = f"T{random.randint(100000, 999999)}"
            if not await Teacher.find_one(Teacher.teacher_id == teacher_id):
                break

        
        # STEP 5 — GENERATE PASSWORD
        
        raw_password = str(random.randint(100000, 999999))
        hashed_password = get_password_hash(raw_password)

        
        # STEP 6 — CREATE TEACHER DOCUMENT
        
        teacher_data = Teacher(
            teacher_id=teacher_id,
            first_name=request_model.first_name,
            middle_name=request_model.middle_name,
            last_name=request_model.last_name,
            email=request_model.email,
            password=hashed_password,
            mobile_number=request_model.mobile_number,
            department=request_model.department,
            subjects_assigned=subjects_to_assign_to_teacher
        )

        await teacher_data.save()

        
        # STEP 7 — ASSIGN TEACHER BACK TO SUBJECT
        
        for subject_doc in subjects_to_assign_to_teacher:
            subject_doc.teacher_assigned = teacher_data
            await subject_doc.save()

        
        # STEP 8 — CLEAR REDIS CACHE
        
        cache_keys = set()
        for subj in subjects_to_assign_to_teacher:
            cache_keys.add(
                f"subjects:{subj.program}:{subj.department}:{subj.semester}"
            )

        for key in cache_keys:
            await redis_client.delete(key)

        await redis_client.delete(f"teacher:{request_model.department}")

        
        # STEP 9 — SEND EMAIL VIA QUEUE
        
        await send_to_queue(
            "email_queue",
            {
                "type": "send_email",
                "data": {
                    "to": request_model.email,
                    "subject": "Teacher Registration Successful",
                    "body": (
                        f"<p>Welcome <strong>{request_model.first_name}</strong>,<br>"
                        f"Your Teacher ID: <strong>{teacher_id}</strong><br>"
                        f"Password: <strong>{raw_password}</strong></p>"
                    )
                }
            },
            priority=5
        )

        
        # STEP 10 — RESPONSE
        
        return JSONResponse(
            status_code=201,
            content={
                "success": True,
                "message": "Teacher created successfully",
                "data": {
                    "teacher_id": teacher_id,
                    "name": f"{request_model.first_name} "
                            f"{request_model.middle_name or ''} "
                            f"{request_model.last_name}".strip(),
                    "email": request_model.email
                }
            }
        )

    
    # ERROR HANDLING
    
    except ValidationError as e:
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "message": "Validation error",
                "details": e.errors()
            }
        )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "Internal server error",
                "error": str(e)
            }
        )
