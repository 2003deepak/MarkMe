import logging
import time
import traceback
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
    logger.info("notify_users: started -- request=%s", {
        "user": request.user,
        "dept": request.dept,
        "program": request.program,
        "semester": request.semester,
        "batch_year": request.batch_year,
        "title": request.title,
        "message" : request.message
    })

    try:
        filter_query: dict = {"active": True}
        user_filter: dict = {}
        user_ids: List = []

        # ------------------------------------------------------------------ #
        # 1. User filtering
        # ------------------------------------------------------------------ #
        logger.debug("Building user_filter for user=%s", request.user)

        # ---------------------- CLERK --------------------------------------
        if request.user == "clerk":
            if request.dept:
                user_filter["department"] = request.dept
            if request.program:
                user_filter["program"] = request.program

            logger.debug("Clerk user_filter=%s", user_filter)

            clerk_docs = await Clerk.find(user_filter).project(EntityIdView).to_list()
            logger.info("Clerk query returned %d docs", clerk_docs)
            user_ids = [doc.id for doc in clerk_docs]

        # ---------------------- TEACHER ------------------------------------
        elif request.user == "teacher":
            if request.dept:
                user_filter["department"] = request.dept

            logger.debug("Teacher user_filter=%s", user_filter)

            teacher_docs = await Teacher.find(user_filter).project(EntityIdView).to_list()
            logger.info("Teacher query returned %d docs", len(teacher_docs))
            user_ids = [doc.id for doc in teacher_docs]

        # ---------------------- STUDENT ------------------------------------
        elif request.user == "student":
            if request.dept:
                user_filter["department"] = request.dept
            if request.program:
                user_filter["program"] = request.program
            if request.semester:
                user_filter["semester"] = request.semester
            if request.batch_year:
                user_filter["batch_year"] = request.batch_year

            logger.debug("Student user_filter=%s", user_filter)

            student_docs = await Student.find(user_filter).project(EntityIdView).to_list()
            logger.info("Student query returned %d docs", len(student_docs))
            user_ids = [doc.id for doc in student_docs]

        else:
            raise HTTPException(status_code=400, detail="Invalid user type")

        logger.info("Total user_ids=%d", len(user_ids))

        if not user_ids:
            return {"success": False, "message": "No users found"}

        filter_query["user_id"] = {"$in": user_ids}
        logger.debug("FCM token filter=%s", filter_query)

        token_docs = await FCMToken.find(filter_query).to_list()
        logger.info("Found %d token docs", len(token_docs))

        tokens = [t.token for t in token_docs if t.active]

        logger.info("Active tokens found=%d", len(tokens))

        if not tokens:
            return {"success": True, "message": "Notifications Done"}

        payload = {
            "tokens": tokens,
            "title": request.title,
            "body": request.message,
            "data": request.data
        }

        logger.debug("Payload prepared with %d tokens", len(tokens))


        logger.info("Publishing to queue...")
        await send_to_queue("notification_queue", payload, priority=5)
        logger.info("Publish success")

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
        logger.error("Full traceback:\n%s", traceback.format_exc())
        raise HTTPException(500, f"Internal server error: {str(exc)}")
