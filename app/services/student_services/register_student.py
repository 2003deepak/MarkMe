from fastapi import HTTPException, UploadFile
from app.core.database import get_db
from datetime import datetime
from passlib.context import CryptContext
from app.schemas.student import Student
from pydantic import ValidationError
from app.utils.security import get_password_hash
from typing import List
from app.utils.publisher import send_to_queue  


async def register_student(student_data: Student, images: List[UploadFile]):
    try:
        
        print("Starting student registration...")

        # Check if student already exists
        if await Student.find_one(Student.email == student_data.email):
            raise HTTPException(
                status_code=400,
                detail={"status": "fail", "message": "Student already exists"}
            )
    

        # Generate student ID
        student_id = f"{student_data.program.upper()}-{student_data.department.upper()}-{student_data.batch_year}-{student_data.semester}-{student_data.roll_number}"

        # Hash password
        hashed_password = get_password_hash(str(student_data.password))

        # Save images temporarily to disk
        image_paths = []
        for image in images:
            path = f"/tmp/{student_id}_{image.filename}"
            with open(path, "wb") as f:
                f.write(await image.read())
            image_paths.append(path)

        # Create student record with empty embedding
        student_doc = Student(
            student_id=student_id,
            first_name=student_data.first_name,
            middle_name=student_data.middle_name,
            last_name=student_data.last_name,
            email=student_data.email,
            password=hashed_password,
            phone=student_data.phone,
            dob=student_data.dob,
            roll_number=student_data.roll_number,
            program=student_data.program,
            department=student_data.department,
            semester=student_data.semester,
            batch_year=student_data.batch_year,
            face_embedding=None  # initially None
        )

        # Save student to database (timestamps are handled by Beanie's pre_save)
        await student_doc.save()

        # ✅ Send Welcome Email Task to Queue
        await send_to_queue("email_queue", {
            "type": "send_email",
            "data": {
                "to": student_data.email,
                "subject": "Welcome to MarkMe!",
                "body": f"Hello {student_data.first_name}, your registration is successful!"
            }
        }, priority=5)  # Medium priority for email

        # ✅ Send Embedding Generation Task to Queue
        await send_to_queue("embedding_queue", {
            "type": "generate_embedding",
            "data": {
                "student_id": student_id,
                "image_paths": image_paths
            }
        }, priority=2)  # Low priority for embedding

        return {
            "status": "success",
            "message": "Student registered successfully",
            "data": {
                "student_id": student_id,
                "name": f"{student_data.first_name} {student_data.middle_name or ''} {student_data.last_name}".strip(),
                "email": student_data.email
            }
        }

    except ValidationError as e:
        error = e.errors()[0]
        loc = ".".join(str(x) for x in error["loc"])
        msg = error["msg"]
        error_msg = f"Invalid {loc}: {msg.lower()}"
        if loc == "password" and "string_too_long" in str(error["type"]):
            error_msg = "Password must be exactly 6 characters"
        elif loc == "password" and "string_too_short" in str(error["type"]):
            error_msg = "Password must be at least 6 characters"

        raise HTTPException(
            status_code=422,
            detail={"status": "fail", "message": error_msg}
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in register_student: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail={"status": "fail", "message": f"Error registering student: {str(e)}"}
        )