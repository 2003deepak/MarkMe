from fastapi import HTTPException, UploadFile, Request
from fastapi.responses import JSONResponse
from app.core.database import get_db
from app.core.redis import redis_client
from datetime import datetime, date
from app.utils.imagekit_uploader import upload_file_to_imagekit, delete_file
from typing import Optional, List
from app.schemas.student import Student
from pydantic import BaseModel, ValidationError, EmailStr
from app.utils.publisher import send_to_queue 
from app.utils.token_utils import create_verification_token
from app.core.config import settings
import base64
from app.models.allModel import UpdateProfileRequest

async def update_student_profile(
    request: Request, 
    request_data: UpdateProfileRequest, 
    images: List[UploadFile] = None, 
    profile_picture: Optional[UploadFile] = None
):
    user_role = request.state.user.get("role")
    user_email = request.state.user.get("email")
    
    print(f"Starting update_student_profile for email: {user_email}")

    # Validate user role
    if user_role != "student":
        print(f"Unauthorized update attempt by role: {user_role}")
        return JSONResponse(
            status_code=403,
            content={
               "success": False,
                "message": "Only Students can access their profile"
            }
        )

    try:
        student_email = user_email
        print(f"Fetching student with email: {student_email}")
        student = await Student.find_one(Student.email == student_email)
        if not student:
            print(f"Student with email {student_email} not found for update.")
            return JSONResponse(
                status_code=404,
                content={
                   "success": False, 
                    "message": "Student not found"
                }
            )

        update_data = {}
        image_paths = []
        # Handle images for face embedding
        
        if images:
            for image in images:
                if not image.content_type.startswith("image/"):
                    print(f"Invalid file type for image: {image.content_type}")
                    return JSONResponse(
                        status_code=400,
                        content={
                           "success": False,
                            "message": "Files must be images"
                        }
                    )
                path = f"C:/Users/deepa/AppData/Local/Temp/{str(student.id)}_{image.filename}"
                with open(path, "wb") as f:
                    f.write(await image.read())
                image_paths.append(path)

            # Send embedding generation task to queue
            await send_to_queue("embedding_queue", {
                "type": "generate_embedding",
                "data": {
                    "student_id": str(student.id),
                    "image_paths": image_paths
                }
            }, priority=2)

        # Handle profile picture
        if profile_picture:
            if not profile_picture.content_type.startswith("image/"):
                return JSONResponse(
                    status_code=400,
                    content={
                       "success": False,
                        "message": "File must be an image"
                    }
                )
            
            # Delete existing profile picture if it exists
            if student.profile_picture_id:
                try:
                    await delete_file(student.profile_picture_id)
                except Exception as e:
                    print(f"Failed to delete existing profile picture: {str(e)}")
                
            file_bytes = await profile_picture.read()
            encoded = base64.b64encode(file_bytes).decode("utf-8")
            
            try:
                profile_picture_result = await upload_file_to_imagekit(
                    file=encoded,
                    filename=profile_picture.filename,
                    folder="profile_image",
                )
                
                if "url" not in profile_picture_result or "fileId" not in profile_picture_result:
                    raise ValueError("Invalid response from image upload service")
                update_data["profile_picture"] = profile_picture_result["url"]
                update_data["profile_picture_id"] = profile_picture_result["fileId"]
            except Exception as e:
                print(f"Image upload error: {str(e)}")
                return JSONResponse(
                    status_code=500,
                    content={
                       "success": False,
                        "message": f"Profile picture upload failed: {str(e)}"
                    }
                )

        # Dynamically update fields if provided
        if request_data.first_name is not None:
            update_data["first_name"] = request_data.first_name
        if request_data.middle_name is not None:
            update_data["middle_name"] = request_data.middle_name
        if request_data.last_name is not None:
            update_data["last_name"] = request_data.last_name
        if request_data.mobile_number is not None:
            update_data["mobile_number"] = request_data.mobile_number
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
            await student.update({"$set": update_data})
            print("Student document updated successfully.")

            # Clear relevant caches
            cache_key_student = f"student:{student_email}"
            await redis_client.delete(cache_key_student)

        else:
            print("No fields to update for student.")

        return JSONResponse(
            status_code=200,
            content={
               "success": True,
                "message": "Student profile updated successfully",
                "data": {
                    "student_id": str(student.id),
                    "name": f"{update_data.get('first_name', student.first_name)} "
                            f"{update_data.get('middle_name', student.middle_name) or ''} "
                            f"{update_data.get('last_name', student.last_name)}".strip()
                }
            }
        )

    except ValidationError as e:
        error = e.errors()[0]
        loc = ".".join(str(x) for x in error["loc"])
        msg = error["msg"]
        error_msg = f"Invalid {loc}: {msg.lower()}"
        print(f"Pydantic validation error: {error_msg}")
        return JSONResponse(
            status_code=422,
            content={
               "success": False, 
                "message": error_msg
            }
        )

    except Exception as e:
        print(f"Unhandled exception during student profile update: {str(e)}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={
               "success": False,
                "message": f"Error updating student profile: {str(e)}"
            }
        )