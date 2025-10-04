from fastapi import HTTPException
from fastapi.responses import JSONResponse
from app.core.database import get_db # This might not be needed if Beanie is initialized globally
from passlib.context import CryptContext
from app.schemas.teacher import Teacher
from app.schemas.subject import Subject
from app.utils.send_email import send_email
from pydantic import ValidationError
from datetime import datetime
from app.core.redis import redis_client
from app.utils.security import get_password_hash
import random
from beanie.operators import In
from beanie import Link # Import Link

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

async def create_teacher(request, request_model):
   
    user_role = request.state.user.get("role")
    if user_role != "clerk":
        print(f"Unauthorized teacher creation attempt by user role: {user_role}")
        return JSONResponse(
            status_code=403,
            content={
                "status": "fail",
                "message": "You don't have the right to create a teacher"
            }
        )

    try:
        # Check if teacher exists
        if await Teacher.find_one(Teacher.email == request_model.email):
            print(f"Teacher with email {request_model.email} already exists.")
            return JSONResponse(
                status_code=409,
                content={
                    "status": "fail",
                    "message": "Teacher already exists"
                }
            )

        # List to hold actual Subject document instances for linking
        subjects_to_assign_to_teacher = []
        if request_model.subjects_assigned:
            # Query for actual Subject documents based on codes
            
            existing_subjects_docs = await Subject.find(
                In(Subject.subject_code, request_model.subjects_assigned)
            ).to_list()

            # Verify that all requested subject codes exist in the database
            found_subject_codes = {subject.subject_code for subject in existing_subjects_docs}
            invalid_subjects = set(request_model.subjects_assigned) - found_subject_codes
            if invalid_subjects:
                print(f"Invalid subject codes provided: {', '.join(invalid_subjects)}")
                return JSONResponse(
                    status_code=400,
                    content={
                        "status": "fail",
                        "message": f"Invalid subject codes: {', '.join(invalid_subjects)}"
                    }
                )
            
            # Store the actual Subject documents for later linking
            subjects_to_assign_to_teacher = existing_subjects_docs
            print(f"Found {len(subjects_to_assign_to_teacher)} valid subjects for assignment.")


        # Generate 6-digit teacher ID starting with "T"
        # Ensure uniqueness if teacher_id is Indexed(unique=True)
        teacher_id = None
        while True:
            generated_id = f"T{random.randint(100000, 999999)}"
            if not await Teacher.find_one(Teacher.teacher_id == generated_id):
                teacher_id = generated_id
                break
        print(f"Generated unique teacher_id: {teacher_id}")

        # Generate 6-digit PIN
        raw_password = str(random.randint(100000, 999999))
        print(f"Generated raw password for {request_model.email}.")

        # Hash the password
        hashed_password = get_password_hash(str(raw_password))

        # Create Teacher Beanie model instance
        teacher_data = Teacher(
            teacher_id=teacher_id,
            first_name=request_model.first_name,
            middle_name=request_model.middle_name,
            last_name=request_model.last_name,
            email=request_model.email,
            password=hashed_password,
            mobile_number=request_model.mobile_number,
            department=request_model.department,
            # Assign actual Subject Document instances. Beanie will convert them to Links.
            subjects_assigned=subjects_to_assign_to_teacher
        )

        # Save teacher to database
        await teacher_data.save()
        print(f"Teacher {teacher_id} saved to database.")

        # Update teacher_assigned in Subject DB with Link to the newly created teacher
        if subjects_to_assign_to_teacher: # Use the list of actual documents
            # Iterate through the fetched subject documents
            for subject_doc in subjects_to_assign_to_teacher:
                # Assign the newly created teacher_data document (Beanie handles linking)
                subject_doc.teacher_assigned = teacher_data
                await subject_doc.save() # Save each updated subject document
            print(f"Assigned teacher {teacher_id} to {len(subjects_to_assign_to_teacher)} subjects.")


        
        unique_subject_cache_keys_to_clear = set()
        for subj in existing_subjects_docs:
            unique_subject_cache_keys_to_clear.add(f"subjects:{subj.program}:{subj.department}:{subj.semester}")
        
        for key in unique_subject_cache_keys_to_clear:
            await redis_client.delete(key)
            print(f"Cleared Redis cache key: {key}")

        await redis_client.delete(f"teacher:{request_model.department}")


        # Send confirmation email with generated password
        try:
            await send_email(
                subject="Your Teacher Account Password",
                email_to=request_model.email,
                body=f"<p>Welcome, {request_model.first_name}!<br>Your password is <strong>{raw_password}</strong>.<br>Your Teacher ID is <strong>{teacher_id}</strong>.</p>"
            )
            print(f"Email sent successfully to {request_model.email}.")
        except Exception as e:
            print(f"Failed to send email to {request_model.email}: {str(e)}")
            # Continue without raising, as email failure shouldn't block registration
            # You might want to log this or add it to a delayed retry queue

        return JSONResponse(
            status_code=201,
            content={
                "status": "success",
                "message": "Teacher created successfully",
                "data": {
                    "teacher_id": teacher_id,
                    "name": f"{request_model.first_name} {request_model.middle_name or ''} {request_model.last_name}".strip(),
                    "email": request_model.email,
                    "generated_password": raw_password # Only return if strictly necessary for the client to display once
                }
            }
        )

    except ValidationError as e:
        error_details = e.errors()
        error_msg = error_details[0]["msg"] if error_details else "Unknown validation error"
        print(f"Pydantic validation error during teacher creation: {error_msg}, Details: {error_details}")
        return JSONResponse(
            status_code=422,
            content={
                "status": "fail",
                "message": f"Validation error: {error_msg}"
            }
        )
    except Exception as e:
        print(f"Unexpected error during teacher creation for {request_model.email}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "fail",
                "message": f"An unexpected error occurred: {str(e)}"
            }
        )