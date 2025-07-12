from fastapi import HTTPException, UploadFile
from app.core.database import get_db
from app.core.redis import redis_client
from app.utils.imagekit_uploader import upload_image_to_imagekit,delete_file
from datetime import datetime
from typing import Optional
import base64
from pydantic import ValidationError

async def update_teacher_profile(request_data, user_data, profile_picture: Optional[UploadFile] = None):
    if user_data["role"] != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can update their profile")

    db = get_db()
    teacher_email = user_data["email"]

    teacher = await db.teachers.find_one({"email": teacher_email})
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")

    update_data = {}

    if profile_picture:
        if not profile_picture.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="File must be an image")
        
        encoded = base64.b64encode(await profile_picture.read()).decode("utf-8")

         # Delete existing profile picture if it exists
        if teacher.get("profile_picture_id"):
            try:
                await delete_file(teacher["profile_picture_id"])
            except Exception as e:
                print(f"Failed to delete existing profile picture: {str(e)}")


        try:
            profile_picture_result = await upload_image_to_imagekit(encoded, "profile_image")

            update_data["profile_picture"] = profile_picture_result.get("url")
            update_data["profile_picture_id"] = profile_picture_result.get("fileId")

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Image upload failed: {str(e)}")

    if request_data.first_name:
        update_data["first_name"] = request_data.first_name
    if request_data.middle_name:
        update_data["middle_name"] = request_data.middle_name
    if request_data.last_name:
        update_data["last_name"] = request_data.last_name
    if request_data.phone:
        update_data["phone"] = request_data.phone

    update_data["updated_at"] = datetime.utcnow()

    if update_data:
        await db.teachers.update_one({"email": teacher_email}, {"$set": update_data})
        await redis_client.delete(f"teacher:{teacher_email}")

    return {"status": "success", "message": "Teacher profile updated successfully"}
