import logging
import time
import traceback
from bson import ObjectId
from fastapi import HTTPException
from typing import List

from app.schemas.fcm import FCMToken
from app.schemas.teacher import Teacher
from app.schemas.student import Student
from app.schemas.clerk import Clerk
from app.utils.publisher import send_to_queue
from app.models.allModel import NotificationRequest, EntityIdView

logger = logging.getLogger(__name__)


async def notify_users(request: NotificationRequest):
    start_ts = time.time()
    logger.info("notify_users: started -- request=%s", request.dict())

    try:
        filter_query = {"active": True}
        user_ids: List[ObjectId] = []

        
        # CASE 1 — target_ids (direct send to specific users)
        
        if request.target_ids:
            logger.info("Target IDs provided → sending only to selected users: %d", len(request.target_ids))

            try:
                user_ids = [ObjectId(uid) for uid in request.target_ids]
            except Exception:
                raise HTTPException(400, "Invalid target_ids: must be valid MongoDB ObjectId")

        
        # CASE 2 — filters array (OR logic)
        
        elif request.filters:
            logger.info("Using filter groups → %d filter blocks", len(request.filters))

            or_conditions = []

            for f in request.filters:
                q = {}

                if f.dept:
                    q["department"] = f.dept
                if f.program:
                    q["program"] = f.program
                if f.semester is not None:
                    q["semester"] = f.semester
                if f.batch_year is not None:
                    q["batch_year"] = f.batch_year

                if q:
                    or_conditions.append(q)

            if not or_conditions:
                return {"success": False, "message": "No valid filters provided"}

            logger.debug("Generated OR filter = %s", or_conditions)

            # Run query depending on user type
            if request.user == "student":
                docs = await Student.find({"$or": or_conditions}).project(EntityIdView).to_list()
            elif request.user == "teacher":
                docs = await Teacher.find({"$or": or_conditions}).project(EntityIdView).to_list()
            elif request.user == "clerk":
                docs = await Clerk.find({"$or": or_conditions}).project(EntityIdView).to_list()
            else:
                raise HTTPException(400, "Invalid user type")

            user_ids = [doc.id for doc in docs]
            logger.info("Filter-based query returned %d users", len(user_ids))

        
        # CASE 3 — No filters, No target_ids → send to ALL users by role
        
        else:
            logger.info("No target_ids and no filters → sending to ALL users of type: %s", request.user)

            if request.user == "student":
                docs = await Student.find({}).project(EntityIdView).to_list()
            elif request.user == "teacher":
                docs = await Teacher.find({}).project(EntityIdView).to_list()
            elif request.user == "clerk":
                docs = await Clerk.find({}).project(EntityIdView).to_list()
            else:
                raise HTTPException(400, "Invalid user type")

            user_ids = [doc.id for doc in docs]

        # Validate user count
        logger.info("Final user_ids count = %d", len(user_ids))

        if not user_ids:
            return {"success": False, "message": "No users found"}

        
        # Fetch FCM tokens
        
        filter_query["user_id"] = {"$in": user_ids}

        token_docs = await FCMToken.find(filter_query).to_list()
        tokens = [t.token for t in token_docs if t.active]

        logger.info("Found %d active tokens", len(tokens))

        if not tokens:
            return {"success": True, "message": "No active device tokens"}

        
        # Prepare payload
        
        payload = {
            "tokens": tokens,
            "title": request.title,
            "body": request.message,
            "data": request.data or {},
        }

        
        # Send to queue
        
        logger.info("Publishing to queue...")
        await send_to_queue("notification_queue", payload, priority=5)

        elapsed = time.time() - start_ts
        logger.info("notify_users completed in %.3f sec", elapsed)

        return {
            "success": True,
            "users_found": len(user_ids),
            "tokens_sent": len(tokens),
            "message": "Notification queued"
        }

    except Exception as exc:
        logger.error("Exception occurred: %s", exc)
        logger.error(traceback.format_exc())
        raise HTTPException(500, f"Internal server error: {str(exc)}")
