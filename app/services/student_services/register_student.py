from fastapi import HTTPException, UploadFile
from app.core.database import get_db
from datetime import datetime
from passlib.context import CryptContext
from app.utils.extract_student_embedding import extract_student_embedding
from app.schemas.student import Student, StudentRepository
from pydantic import ValidationError
from typing import List

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

async def register_student(student_data: Student, images: List[UploadFile]):
    try:
        # Get database connection
        db = get_db()
        repo = StudentRepository(db.client, db.name)

        # Check if student exists
        if await db.students.find_one({"email": student_data.email}):
            raise HTTPException(
                status_code=400,
                detail={
                    "status": "fail",
                    "message": "Student already exists"
                }
            )

        # Generate face embedding
        try:
            face_embedding = await extract_student_embedding(images)
            face_embedding_list = face_embedding.tolist()
        except Exception as e:
            print(f"Face embedding error: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail={
                    "status": "fail",
                    "message": "Error processing face embeddings"
                }
            )

        # Generate student ID
        student_id = f"{student_data.program.upper()}-{student_data.department.upper()}-{student_data.batch_year}-{student_data.semester}-{student_data.roll_number}"

        # Hash the password
        hashed_password = pwd_context.hash(str(student_data.password))

        # Create student document
        student_doc = Student(
            student_id=student_id,
            first_name=student_data.first_name,
            middle_name=student_data.middle_name,
            last_name=student_data.last_name,
            email=student_data.email,
            password=hashed_password,
            phone=student_data.phone,
            dob=student_data.dob,  # Keep as datetime, validate in model
            roll_number=student_data.roll_number,
            program=student_data.program,
            department=student_data.department,
            semester=student_data.semester,
            batch_year=student_data.batch_year,
            face_embedding=face_embedding_list,
        )

        # Convert to dict and apply timestamps
        student_dict = student_doc.dict()
        student_dict = await repo._apply_timestamps(student_dict)

        # Insert document
        await db.students.insert_one(student_dict)

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
        loc = ".".join(str(x) for x in error["loc"])  # Convert loc to string
        msg = error["msg"]
        error_msg = f"Invalid {loc}: {msg.lower()}"
        if loc == "password" and "string_too_long" in str(error["type"]):
            error_msg = "Password must be exactly 6 characters"
        elif loc == "password" and "string_too_short" in str(error["type"]):
            error_msg = "Password must be at least 6 characters"

        raise HTTPException(
            status_code=422,
            detail={
                "status": "fail",
                "message": error_msg
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Student Creation error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={
                "status": "fail",
                "message": f"Error registering student: {str(e)}"
            }
        )