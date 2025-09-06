from fastapi import HTTPException, UploadFile, File
from app.core.database import get_db
from app.core.redis import redis_client
from datetime import datetime
from app.utils.imagekit_uploader import upload_image_to_imagekit, delete_file
from typing import Optional, List
from app.schemas.student import Student
from pydantic import ValidationError
from app.utils.security import get_password_hash
from app.utils.publisher import send_to_queue 
import httpx
import base64


async def update_student_profile(request_data, user_data, images: List[UploadFile] = None):
    print(f"Starting update_student_profile for email: {user_data['email']}")

    # Validate user role
    if user_data["role"] != "student":
        print(f"Unauthorized update attempt by role: {user_data['role']}")
        raise HTTPException(
            status_code=403,
            detail="Only Students can access their profile"
        )

    try:
        student_email = user_data["email"]
        print(f"Fetching student with email: {student_email}")
        student = await Student.find_one(Student.email == student_email)
        if not student:
            print(f"Student with email {student_email} not found for update.")
            raise HTTPException(
                status_code=404,
                detail={"status": "fail", "message": "Student not found"},
            )
        print(f"Student found: {student.student_id}")

        # Check if email is being updated and already exists
        if request_data.email and request_data.email != student_email:
            if await Student.find_one(Student.email == request_data.email):
                raise HTTPException(
                    status_code=400,
                    detail={"status": "fail", "message": "Email already in use"}
                )

        update_data = {}
        student_id_changed = False
    
        # Handle password hashing
        if request_data.password:
            update_data["password"] = get_password_hash(str(request_data.password))

        # Handle images for face embedding
        image_paths = []
        if images:
            for image in images:
                if not image.content_type.startswith("image/"):
                    print(f"Invalid file type for image: {image.content_type}")
                    raise HTTPException(
                        status_code=400,
                        detail={"status": "fail", "message": "Files must be images"}
                    )
                path = f"/tmp/{student.student_id}_{image.filename}"
                with open(path, "wb") as f:
                    f.write(await image.read())
                image_paths.append(path)

            # Send embedding generation task to queue
            await send_to_queue("embedding_queue", {
                "type": "generate_embedding",
                "data": {
                    "student_id": update_data.get("student_id", student.student_id),
                    "image_paths": image_paths
                }
            }, priority=2)

        # Dynamically update fields if provided
        if request_data.first_name is not None:
            update_data["first_name"] = request_data.first_name
        if request_data.middle_name is not None:
            update_data["middle_name"] = request_data.middle_name
        if request_data.last_name is not None:
            update_data["last_name"] = request_data.last_name
        if request_data.email is not None:
            update_data["email"] = request_data.email
        if request_data.phone is not None:
            update_data["phone"] = request_data.phone
        if request_data.dob is not None:
            update_data["dob"] = request_data.dob
        if request_data.roll_number is not None:
            update_data["roll_number"] = request_data.roll_number
        if request_data.program is not None:
            update_data["program"] = request_data.program
        if request_data.department is not None:
            update_data["department"] = request_data.department
        if request_data.semester is not None:
            update_data["semester"] = request_data.semester
        if request_data.batch_year is not None:
            update_data["batch_year"] = request_data.batch_year

        update_data["updated_at"] = datetime.utcnow()

        # Only update if there's something to update
        if update_data:
            print(f"Update data prepared: {update_data}")
            await student.update({"$set": update_data})
            print("Student document updated successfully.")

            # Clear relevant caches
            cache_key_student = f"student:{student_email}"
            await redis_client.delete(cache_key_student)
            
            # Clear program-specific cache if student ID changed
            if student_id_changed:
                cache_key = f"student:{student.department.upper()}:{student.program.upper()}:{student.semester}"
                await redis_client.delete(cache_key)
                print(f"Deleted program cache: {cache_key}")

        else:
            print("No fields to update for student.")

        return {
            "status": "success",
            "message": "Student profile updated successfully",
            "data": {
                "student_id": update_data.get("student_id", student.student_id),
                "name": f"{update_data.get('first_name', student.first_name)} "
                        f"{update_data.get('middle_name', student.middle_name) or ''} "
                        f"{update_data.get('last_name', student.last_name)}".strip(),
                "email": update_data.get("email", student.email)
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
        print(f"Pydantic validation error: {error_msg}")
        raise HTTPException(status_code=422, detail={"status": "fail", "message": error_msg})

    except HTTPException:
        print("HTTPException raised during student profile update.")
        raise

    except Exception as e:
        print(f"Unhandled exception during student profile update: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail={"status": "fail", "message": f"Error updating student profile: {str(e)}"}
        )