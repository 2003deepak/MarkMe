import os
import uuid
import logging
import tempfile
import aiofiles
from datetime import datetime
from typing import Optional, List
from fastapi import UploadFile, Request
from fastapi.responses import JSONResponse

from app.schemas.student import Student
from app.core.redis import redis_client
from app.utils.imagekit_uploader import upload_file_to_imagekit, delete_file
from app.utils.publisher import send_to_queue
from app.utils.security import create_access_token
from app.models.allModel import UpdateProfileRequest
from app.core.faiss_cache import faiss_cache, get_cache_key

logger = logging.getLogger(__name__)

async def update_student_profile(
    request: Request,
    request_data: UpdateProfileRequest,
    images: List[UploadFile] = None,
    profile_picture: Optional[UploadFile] = None
):
    user_role = request.state.user.get("role")
    user_email = request.state.user.get("email")

    if user_role != "student":
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Only Students can access their profile"}
        )

    try:
        
      
        student = await Student.find_one(Student.email == user_email)
        if not student:
            return JSONResponse(
                status_code=404, 
                content={"success": False, "message": "Student not found"}
            )

        update_data = {}
        
        # --- Handle Face Images ---
        if images:
            if not (3 <= len(images) <= 4):
                return JSONResponse(
                    status_code=400, 
                    content={"success": False, "message": "Upload exactly 3 to 4 images"}
                )

            image_paths = []
            temp_dir = tempfile.gettempdir()
            for image in images:
                if not image.content_type.startswith("image/"):
                    return JSONResponse(status_code=400, content={"success": False, "message": "Files must be images"})
                
                content = await image.read()
                filename = f"{uuid.uuid4()}.jpg"
                path = os.path.join(temp_dir, filename)
                async with aiofiles.open(path, "wb") as f:
                    await f.write(content)
                image_paths.append(path)

            await send_to_queue("embedding_queue", {
                "type": "generate_embedding",
                "data": {"student_id": str(student.id), "image_paths": image_paths}
            }, priority=2)

        # --- Handle Profile Picture ---
        if profile_picture:
            if not profile_picture.content_type.startswith("image/"):
                return JSONResponse(status_code=400, content={"success": False, "message": "File must be an image"})

            if student.profile_picture_id:
                try:
                    await delete_file(student.profile_picture_id)
                except Exception as e:
                    logger.warning(f"Old profile delete failed: {e}")

            file_bytes = await profile_picture.read()
            try:
                result = await upload_file_to_imagekit(
                    file=file_bytes,
                    filename=f"{uuid.uuid4()}.jpg",
                    folder="profile_image"
                )
                update_data["profile_picture"] = result["url"]
                update_data["profile_picture_id"] = result["fileId"]
            except Exception as e:
                logger.error(f"ImageKit upload failed: {e}")
                return JSONResponse(status_code=500, content={"success": False, "message": "Upload failed"})

        # --- Update Fields ---
        fields = ["first_name", "middle_name", "last_name", "dob", "roll_number", "program", "department", "semester", "batch_year"]
        for field in fields:
            val = getattr(request_data, field)
            if val is not None:
                update_data[field] = val
        
        if request_data.phone:
            update_data["phone"] = request_data.phone

        if update_data:
            update_data["updated_at"] = datetime.utcnow()
            old_cache_key = get_cache_key(student.semester, student.department, student.program)
            
            await student.update({"$set": update_data})
            
            new_cache_key = get_cache_key(
                update_data.get("semester", student.semester),
                update_data.get("department", student.department),
                update_data.get("program", student.program)
            )

            faiss_cache.pop(old_cache_key, None)
            faiss_cache.pop(new_cache_key, None)
            await redis_client.delete(f"student:{student.email}")
            student = await Student.get(student.id)
            

        # --- Generate New Token ---
        new_token = create_access_token({
            "id": str(student.id),
            "email": student.email,
            "role": "student",
            "roll_number": student.roll_number,
            "program": student.program,
            "department": student.department,
            "semester": student.semester,
            "batch_year": student.batch_year
        })

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Profile updated successfully",
                "data": {
                    "student_id": str(student.id),
                    "name": f"{student.first_name} {student.last_name}".strip(),
                    "access_token": new_token
                }
            }
        )

    except Exception as e:
        logger.error(f"Update failed: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"success": False, "message": "Internal server error"})