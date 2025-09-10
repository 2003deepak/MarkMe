from typing import Optional, List
from fastapi import HTTPException, UploadFile
from pydantic import ValidationError
from datetime import datetime
import os
import json
import logging
import base64
from app.schemas.clerk import Clerk  
from app.core.redis import redis_client
from app.core.config import settings  
from app.models.allModel import UpdateClerkRequest
from app.utils.imagekit_uploader import upload_image_to_imagekit, delete_file

async def update_clerk(request_data: UpdateClerkRequest, user_data: dict, profile_picture: Optional[UploadFile] = None):
    print(f"Starting update_clerk for email: {user_data['email']}")

    # Validate user role
    if user_data["role"] != "clerk":
        print(f"Unauthorized update attempt by role: {user_data['role']}")
        raise HTTPException(
            status_code=403,
            detail="Only clerks can access their profile"
        )

    try:
        clerk_email = user_data["email"]
        print(f"Fetching clerk with email: {clerk_email}")
        try:
            clerk = await Clerk.find_one(Clerk.email == clerk_email)
        except ValidationError as e:
            print(f"Invalid clerk data for email {clerk_email}: {str(e)}")
            raise HTTPException(
                status_code=400,
                detail={"status": "fail", "message": f"Invalid clerk data in database: {str(e)}"}
            )
        if not clerk:
            print(f"Clerk with email {clerk_email} not found for update.")
            raise HTTPException(
                status_code=404,
                detail={"status": "fail", "message": "Clerk not found"}
            )
        print(f"Clerk found: {clerk.email}")

        update_data = {}
        department_changed = False
        program_changed = False
        old_department = clerk.department
        old_program = clerk.program

        # Dynamically update fields if provided
        if request_data.first_name is not None:
            update_data["first_name"] = request_data.first_name
        if request_data.middle_name is not None:
            update_data["middle_name"] = request_data.middle_name
        if request_data.last_name is not None:
            update_data["last_name"] = request_data.last_name
        if request_data.phone is not None:
            update_data["phone"] = request_data.phone
        if request_data.department is not None:
            if request_data.department != clerk.department:
                department_changed = True
            update_data["department"] = request_data.department
        if request_data.program is not None:
            if request_data.program != clerk.program:
                program_changed = True
            update_data["program"] = request_data.program

        # Handle profile picture
        if profile_picture:
            if not profile_picture.content_type.startswith("image/"):
                print(f"Invalid file type for profile_picture: {profile_picture.content_type}")
                raise HTTPException(
                    status_code=400,
                    detail={"status": "fail", "message": "File must be an image"}
                )

            # Delete existing profile picture if it exists
            if clerk.profile_picture_id:
                try:
                    await delete_file(clerk.profile_picture_id)
                    print(f"Deleted existing profile picture: {clerk.profile_picture_id}")
                except Exception as e:
                    print(f"Failed to delete existing profile picture: {str(e)}")

            file_bytes = await profile_picture.read()
            encoded = base64.b64encode(file_bytes).decode("utf-8")

            try:
                profile_picture_result = await upload_image_to_imagekit(
                    file=encoded,
                    folder="profile_image",
                )
                if "url" not in profile_picture_result or "fileId" not in profile_picture_result:
                    raise ValueError("Invalid response from image upload service")
                update_data["profile_picture"] = profile_picture_result["url"]
                update_data["profile_picture_id"] = profile_picture_result["fileId"]
            except Exception as e:
                print(f"Image upload error: {str(e)}")
                raise HTTPException(
                    status_code=500,
                    detail={"status": "fail", "message": f"Profile picture upload failed: {str(e)}"}
                )

        update_data["updated_at"] = datetime.utcnow()

        # Only update if there's something to update
        if update_data:
            print(f"Update data prepared: {update_data}")
            await clerk.update({"$set": update_data})
            print("Clerk document updated successfully.")

            # Clear relevant caches
            cache_key_clerk = f"clerk:{clerk_email}"
            await redis_client.delete(cache_key_clerk)
            print(f"Deleted cache key: {cache_key_clerk}")

            # Clear department-specific cache
            if clerk.department:
                cache_key_department = f"clerks:{clerk.department.upper()}"
                await redis_client.delete(cache_key_department)
                print(f"Deleted department cache key: {cache_key_department}")

            # If department changed, clear the new and old department caches
            if department_changed:
                if request_data.department:
                    cache_key_new_department = f"clerks:{request_data.department.upper()}"
                    await redis_client.delete(cache_key_new_department)
                    print(f"Deleted new department cache key: {cache_key_new_department}")
                if old_department and old_department != request_data.department:
                    cache_key_old_department = f"clerks:{old_department.upper()}"
                    await redis_client.delete(cache_key_old_department)
                    print(f"Deleted old department cache key: {cache_key_old_department}")

            # Clear program-specific cache (assuming clerks:{program} exists)
            if clerk.program:
                cache_key_program = f"clerks:{clerk.program.upper()}"
                await redis_client.delete(cache_key_program)
                print(f"Deleted program cache key: {cache_key_program}")

            # If program changed, clear the new and old program caches
            if program_changed:
                if request_data.program:
                    cache_key_new_program = f"clerks:{request_data.program.upper()}"
                    await redis_client.delete(cache_key_new_program)
                    print(f"Deleted new program cache key: {cache_key_new_program}")
                if old_program and old_program != request_data.program:
                    cache_key_old_program = f"clerks:{old_program.upper()}"
                    await redis_client.delete(cache_key_old_program)
                    print(f"Deleted old program cache key: {cache_key_old_program}")

        else:
            print("No fields to update for clerk.")

        return {
            "status": "success",
            "message": "Clerk profile updated successfully",
            "data": {
                "email": clerk.email,
                "name": f"{update_data.get('first_name', clerk.first_name)} "
                        f"{update_data.get('middle_name', clerk.middle_name) or ''} "
                        f"{update_data.get('last_name', clerk.last_name)}".strip(),
                "department": update_data.get("department", clerk.department),
                "program": update_data.get("program", clerk.program)
            }
        }

    except HTTPException:
        print("HTTPException raised during clerk profile update.")
        raise

    except Exception as e:
        print(f"Unhandled exception during clerk profile update: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail={"status": "fail", "message": f"Error updating clerk profile: {str(e)}"}
        )