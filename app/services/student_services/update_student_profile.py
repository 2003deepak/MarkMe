from fastapi import HTTPException, UploadFile
from app.core.database import get_db
from app.core.redis import redis_client
from datetime import datetime
from app.utils.imagekit_uploader import upload_image_to_imagekit,delete_file
from typing import Optional
from pydantic import ValidationError
import httpx
import base64

async def update_student_profile(request_data, user_data, profile_picture: Optional[UploadFile] = None):
    
     # Validate user role
    if user_data["role"] != "student":
        raise HTTPException(
            status_code=403,
            detail="Only Students can access their profile"
        )
    
    try:
        db = get_db()
        student_email = user_data["email"]

        # Fetch existing student
        student = await db.students.find_one({"email": student_email})
        if not student:
            raise HTTPException(
                status_code=404,
                detail={"status": "fail", "message": "Student not found"},
            )

        update_data = {}

        if profile_picture:
            if not profile_picture.content_type.startswith("image/"):
                raise HTTPException(
                    status_code=400,
                    detail={"status": "fail", "message": "File must be an image"}
                )
            
            # Delete existing profile picture if it exists
            if student.get("profile_picture_id"):
                try:
                    await delete_file(student["profile_picture_id"])
                except Exception as e:
                    print(f"Failed to delete existing profile picture: {str(e)}")
                    

            
            file_bytes = await profile_picture.read()
            encoded = base64.b64encode(file_bytes).decode("utf-8")
            

            try:
                profile_picture_result = await upload_image_to_imagekit(
                    file=encoded,
                    folder="profile_image",
                )
                update_data["profile_picture"] = profile_picture_result.get("url")
                update_data["profile_picture_id"] = profile_picture_result.get("fileId")

            except Exception as e:
                print(f"Image upload error (file): {str(e)}")
                raise HTTPException(
                    status_code=500,
                    detail={"status": "fail", "message": f"Profile picture upload failed: {str(e)}"}
                )

        # Dynamically update fields if provided
        if request_data.first_name:
            update_data["first_name"] = request_data.first_name
        if request_data.middle_name:
            update_data["middle_name"] = request_data.middle_name
        if request_data.last_name:
            update_data["last_name"] = request_data.last_name
        if request_data.phone:
            update_data["phone"] = request_data.phone
        if request_data.dob:
            update_data["dob"] = request_data.dob

        update_data["updated_at"] = datetime.utcnow()

        # Only update if there's something to update
        if update_data:
            await db.students.update_one(
                {"email": student_email},
                {"$set": update_data}
            )

        updated_student = await db.students.find_one({"email": student_email})

        # Remove the redis cache for the user to get the updated data
        cache_key_student = f"student:{student_email}"
        await redis_client.delete(cache_key_student)

        return {
            "status": "success",
            "message": "Student profile updated successfully"
        }

    except ValidationError as e:
        error = e.errors()[0]
        loc = ".".join(str(x) for x in error["loc"])
        msg = error["msg"]
        error_msg = f"Invalid {loc}: {msg.lower()}"
        raise HTTPException(status_code=422, detail={"status": "fail", "message": error_msg})

    except HTTPException:
        raise

    except Exception as e:
        print(f"Student profile update error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={"status": "fail", "message": f"Error updating student profile: {str(e)}"}
        )