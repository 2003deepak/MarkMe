from fastapi import HTTPException
from app.core.database import get_db
from passlib.context import CryptContext
from app.schemas.teacher import Teacher, TeacherRepository
from app.utils.send_email import send_email
from pydantic import ValidationError
from datetime import datetime
import random

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

async def create_teacher(request,user_data):

    if user_data["role"] != "clerk" :
        raise HTTPException(
                status_code=400,
                detail={
                    "status": "fail",
                    "message": "You Dont have right to create clerk"
                }
            )



    try:
        # Get database connection
        db = get_db()
        repo = TeacherRepository(db.client, db.name)

        # Check if teacher exists
        if await db.teachers.find_one({"email": request.email}):
            raise HTTPException(
                status_code=400,
                detail={
                    "status": "fail",
                    "message": "Teacher already exists"
                }
            )

        # Check if subjects_assigned match existing subjects in DB
        existing_subjects = []
        if request.subjects_assigned:
            existing_subjects_cursor = db.subjects.find({"subject_code": {"$in": request.subjects_assigned}})
            existing_subjects = await existing_subjects_cursor.to_list(length=None)

            # print(existing_subjects)
            
            if len(existing_subjects) != len(request.subjects_assigned):
                existing_subject_codes = {s["subject_code"] for s in existing_subjects}
                invalid_subjects = set(request.subjects_assigned) - existing_subject_codes
                raise HTTPException(
                    status_code=400,
                    detail={
                        "status": "fail",
                        "message": f"Invalid subject codes: {', '.join(invalid_subjects)}"
                    }
                )

        # Generate 6-digit teacher ID starting with "T"
        teacher_id = f"T{random.randint(100000, 999999)}"

        # Generate 6-digit PIN
        raw_password = str(random.randint(100000, 999999))

        # Hash the password
        hashed_password = pwd_context.hash(raw_password)

        # Validate and create Teacher object
        teacher_data = Teacher(
            teacher_id=teacher_id,
            first_name=request.first_name,
            middle_name=request.middle_name,
            last_name=request.last_name,
            email=request.email,
            password=hashed_password,
            mobile_number=request.mobile_number,
            department=request.department,
            subjects_assigned=[str(subject["_id"]) for subject in existing_subjects]  # Store subject _id values
        )

        # Convert to dict and apply timestamps
        teacher_dict = teacher_data.dict()
        teacher_dict = await repo._apply_timestamps(teacher_dict)

        # Insert teacher into database
        result = await db.teachers.insert_one(teacher_dict)
        teacher_id_str = str(result.inserted_id)  # Get the _id as string

        # Populate teacher_assigned in Subject DB with teacher _id
        if request.subjects_assigned:
            for subject_code in request.subjects_assigned:
                await db.subjects.update_one(
                    {"subject_code": subject_code},
                    {"$addToSet": {"teacher_assigned": teacher_id_str}}
                )

        # Send confirmation email with generated password
        try:
            await send_email(
                subject="Your Teacher Account Password",
                email_to=request.email,
                body=f"<p>Welcome, {request.first_name}!<br>Your password is <strong>{raw_password}</strong>.</p>"
            )
        except Exception as e:
            print(f"Failed to send email to {request.email}: {str(e)}")
            # Continue without raising, as email failure shouldn't block registration

        return {
            "status": "success",
            "message": "Teacher created successfully",
            "data": {
                "teacher_id": teacher_id,
                "name": f"{request.first_name} {request.middle_name or ''} {request.last_name}".strip(),
                "email": request.email,
                "generated_password": raw_password
            }
        }

    except ValidationError as e:
        print(e)
        error_msg = str(e.errors()[0]['msg'])

        raise HTTPException(
            status_code=422,
            detail={
                "status": "fail",
                "message": f"Validation error: {error_msg}"
            }
        )
    except HTTPException as he:
        if isinstance(he.detail, dict) and "status" in he.detail and "message" in he.detail:
            raise he
        raise HTTPException(
            status_code=he.status_code,
            detail={
                "status": "fail",
                "message": str(he.detail)
            }
        )
    except Exception as e:
        print(f"Teacher creation error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={
                "status": "fail",
                "message": f"Error creating teacher: {str(e)}"
            }
        )