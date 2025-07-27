from fastapi import HTTPException, UploadFile
from app.core.database import get_db
from app.core.redis import redis_client
from datetime import datetime
from app.utils.imagekit_uploader import upload_image_to_imagekit,delete_file
from typing import Optional
from app.schemas.student import Student
from pydantic import ValidationError
import httpx
import base64


async def update_student_profile(request_data, user_data, profile_picture: Optional[UploadFile] = None):
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

        update_data = {}

        if profile_picture:
            print(f"Profile picture received. Filename: {profile_picture.filename}, Content Type: {profile_picture.content_type}")
            if not profile_picture.content_type.startswith("image/"):
                print(f"Invalid file type for profile picture: {profile_picture.content_type}")
                raise HTTPException(
                    status_code=400,
                    detail={"status": "fail", "message": "File must be an image"}
                )

            # Check if file content is empty (e.g., if "Choose File" was clicked but no file selected)
            # You might want to skip upload if the file is genuinely empty.
            initial_pos = await profile_picture.tell() # Store current position
            file_bytes = await profile_picture.read()
            await profile_picture.seek(initial_pos) # Reset position for future reads if needed
            if not file_bytes:
                print("Profile picture input is empty (no bytes). Skipping upload.")
                # If they passed an empty file, maybe they want to clear current pic?
                # Your current logic will keep existing if no new one is uploaded
                # and no specific instruction to delete.
                profile_picture_to_upload = None
            else:
                profile_picture_to_upload = profile_picture

            if profile_picture_to_upload:
                print("Processing profile picture for upload.")
                # Delete existing profile picture if it exists
                if student.profile_picture_id:
                    print(f"Deleting existing profile picture with ID: {student.profile_picture_id}")
                    try:
                        await delete_file(student.profile_picture_id)
                        print("Existing profile picture deleted successfully.")
                    except Exception as e:
                        print(f"Failed to delete existing profile picture (non-critical, continuing): {str(e)}")

                encoded = base64.b64encode(file_bytes).decode("utf-8")
                
                print("Uploading new profile picture to ImageKit.")
                try:
                    profile_picture_result = await upload_image_to_imagekit(
                        file=encoded,
                        folder="profile_image",
                    )
                    update_data["profile_picture"] = profile_picture_result.get("url")
                    update_data["profile_picture_id"] = profile_picture_result.get("fileId")
                    print(f"Profile picture uploaded: {update_data['profile_picture']}")

                except Exception as e:
                    print(f"Image upload error (file): {str(e)}", exc_info=True)
                    raise HTTPException(
                        status_code=500,
                        detail={"status": "fail", "message": f"Profile picture upload failed: {str(e)}"}
                    )
            else:
                # If profile_picture was an empty UploadFile and we explicitly decided not to upload
                # You might want to add logic here to explicitly remove the profile picture if desired.
                # For example, if the user explicitly 'cleared' their picture without uploading a new one.
                # Currently, if profile_picture_to_upload is None, update_data won't have 'profile_picture' fields.
                # If you want to allow clearing the picture, you'd need an explicit flag or a magic value.
                pass


        # Dynamically update fields if provided
        print("Processing other profile fields.")
        if request_data.first_name is not None: # Check for None explicitly
            update_data["first_name"] = request_data.first_name
        if request_data.middle_name is not None:
            update_data["middle_name"] = request_data.middle_name
        if request_data.last_name is not None:
            update_data["last_name"] = request_data.last_name
        if request_data.phone is not None:
            update_data["phone"] = request_data.phone
        if request_data.dob is not None:
            update_data["dob"] = request_data.dob

        update_data["updated_at"] = datetime.utcnow()
        print(f"Update data prepared: {update_data}")

        # Only update if there's something to update
        if update_data:
            print("Updating student document in MongoDB.")
            await student.update({"$set": update_data})
            print("Student document updated successfully.")
        else:
            print("No fields to update for student.")

        # Remove the redis cache for the user to get the updated data
        cache_key_student = f"student:{student_email}"
        print(f"Deleting Redis cache for student: {cache_key_student}")
        await redis_client.delete(cache_key_student)
        print("Redis cache deleted.")

        return {
            "status": "success",
            "message": "Student profile updated successfully"
        }

    except ValidationError as e:
        error = e.errors()[0]
        loc = ".".join(str(x) for x in error["loc"])
        msg = error["msg"]
        error_msg = f"Invalid {loc}: {msg.lower()}"
        print(f"Pydantic validation error: {error_msg}", exc_info=True)
        raise HTTPException(status_code=422, detail={"status": "fail", "message": error_msg})

    except HTTPException:
        print("HTTPException raised during student profile update.", exc_info=True)
        raise

    except Exception as e:
        print(f"Unhandled exception during student profile update: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"status": "fail", "message": f"Error updating student profile: {str(e)}"}
        )