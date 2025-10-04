from fastapi import HTTPException, UploadFile, Request
from fastapi.responses import JSONResponse
from app.core.redis import redis_client
from app.models.allModel import UpdateProfileRequest
from app.utils.imagekit_uploader import upload_image_to_imagekit, delete_file
from datetime import datetime
from typing import Optional
import base64
from pydantic import ValidationError
from app.schemas.teacher import Teacher
from pydantic import BaseModel, validator



async def update_teacher_profile(
    request: Request, 
    request_data: UpdateProfileRequest, 
    profile_picture: Optional[UploadFile] = None
):
    user_role = request.state.user.get("role")
    user_email = request.state.user.get("email")
    
    if user_role != "teacher":
        return JSONResponse(
            status_code=403,
            content={
                "status": "fail",
                "message": "Only teachers can update their profile"
            }
        )

    teacher_email = user_email
    teacher = await Teacher.find_one(Teacher.email == teacher_email)
    if not teacher:
        return JSONResponse(
            status_code=404,
            content={
                "status": "fail",
                "message": "Teacher not found"
            }
        )

    update_data = {}

    # Handle profile picture upload
    if profile_picture:
        if not profile_picture.content_type.startswith("image/"):
            return JSONResponse(
                status_code=400,
                content={
                    "status": "fail",
                    "message": "File must be an image"
                }
            )
        
        # Read and encode the file
        file_bytes = await profile_picture.read()
        encoded = base64.b64encode(file_bytes).decode("utf-8")

        # Delete existing profile picture if it exists
        if teacher.profile_picture_id:
            try:
                await delete_file(teacher.profile_picture_id)
                print(f"Deleted existing profile picture: {teacher.profile_picture_id}")
            except Exception as e:
                print(f"Failed to delete existing profile picture: {str(e)}")

        try:
            profile_picture_result = await upload_image_to_imagekit(
                file=encoded, 
                folder="profile_image"
            )
            
            if "url" not in profile_picture_result or "fileId" not in profile_picture_result:
                raise ValueError("Invalid response from image upload service")
                
            update_data["profile_picture"] = profile_picture_result["url"]
            update_data["profile_picture_id"] = profile_picture_result["fileId"]
            print(f"Uploaded new profile picture: {profile_picture_result['fileId']}")
            
        except Exception as e:
            print(f"Image upload error: {str(e)}")
            return JSONResponse(
                status_code=500,
                content={
                    "status": "fail",
                    "message": f"Profile picture upload failed: {str(e)}"
                }
            )

    # Update basic profile fields
    if request_data.first_name is not None:
        update_data["first_name"] = request_data.first_name
    if request_data.middle_name is not None:
        update_data["middle_name"] = request_data.middle_name
    if request_data.last_name is not None:
        update_data["last_name"] = request_data.last_name
    if request_data.mobile_number is not None:
        # Convert to integer for storage
        try:
            update_data["mobile_number"] = int(request_data.mobile_number)
        except (ValueError, TypeError):
            return JSONResponse(
                status_code=422,
                content={
                    "status": "fail",
                    "message": "Invalid mobile number format"
                }
            )

    update_data["updated_at"] = datetime.utcnow()

    # Only update if there's something to update
    if update_data:
        print(f"Update data prepared: {update_data}")
        await teacher.update({"$set": update_data})
        print("Teacher document updated successfully.")

        # Clear relevant caches
        cache_key_teacher = f"teacher:{teacher_email}"
        await redis_client.delete(cache_key_teacher)
        print(f"Deleted cache key: {cache_key_teacher}")

        # Clear department cache if teacher has department
        if teacher.department:
            cache_key_department = f"teachers:{teacher.department}"
            await redis_client.delete(cache_key_department)
            print(f"Deleted department cache key: {cache_key_department}")

    else:
        print("No fields to update for teacher.")

    # Prepare response data
    response_data = {
        "status": "success",
        "message": "Teacher profile updated successfully",
        "data": {
            "teacher_id": teacher.teacher_id,
            "name": f"{update_data.get('first_name', teacher.first_name)} "
                    f"{update_data.get('middle_name', teacher.middle_name) or ''} "
                    f"{update_data.get('last_name', teacher.last_name)}".strip(),
            "email": teacher.email,
            "mobile_number": update_data.get("mobile_number", teacher.mobile_number)
        }
    }

    return JSONResponse(
        status_code=200,
        content=response_data
    )