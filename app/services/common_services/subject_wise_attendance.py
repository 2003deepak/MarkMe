from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from bson import ObjectId
import json
import logging
from datetime import datetime
from typing import Dict, Any

from app.schemas.subject_session_stats import SubjectSessionStats  # Beanie Document

# --- JSON encoder for ObjectId & datetime ---
class MongoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


# --- Controller function ---
async def subject_wise_attendance(request: Request, subject_id: str) -> JSONResponse:
    """
    Fetch average student attendance for a specific subject.
    """

    try:
        # --- Authorization check ---
        user_role = request.state.user.get("role")
        logging.info(f"🔍 User role check: {user_role} for subject_id: {subject_id}")
        if user_role not in {"admin", "clerk", "teacher"}:
            logging.warning(f"🚫 Unauthorized access attempt by role: {user_role}")
            raise HTTPException(status_code=403, detail="Unauthorized access")

        # --- Validate subject_id ---
        logging.info(f"📋 Validating subject_id: {subject_id}")
        if not ObjectId.is_valid(subject_id):
            logging.error(f"❌ Invalid ObjectId: {subject_id}")
            return JSONResponse(
                status_code=400,
                content={
                    "status": "fail",
                    "message": "Invalid subject ID format.",
                    "data": {},
                },
            )
        validated_oid = ObjectId(subject_id)
        logging.info(f"✅ Valid ObjectId: {validated_oid}")

        # --- Fetch session stats for this subject ---
        logging.info(f"🔍 Executing query for SubjectSessionStats where subject.id == {validated_oid}")
        results = await SubjectSessionStats.find(
             SubjectSessionStats.subject.id == validated_oid
        ).to_list()
        logging.info(f"📊 Query completed. Found {len(results)} records")

        if not results:
            logging.warning(f"⚠️ No results found for subject_id: {subject_id}. Check if data exists in collection.")
            # Optional: Log a sample query in raw MongoDB format for debugging
            logging.debug(f"Raw MongoDB query equivalent: {{ 'subject': {{ '$ref': 'subjects', '$id': {validated_oid} }} }}")
            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "message": "No attendance data found for this subject.",
                    "data": {},
                },
            )

        # Log first record for structure inspection (if exists)
        if results:
            logging.info(f"🔍 Sample record structure: {json.dumps(results[0].model_dump(), default=str, indent=2)}")

        # --- Compute average attendance ---
        logging.info(f"🧮 Starting attendance calculation for {len(results)} sessions")
        total_attendance = 0.0
        count = 0

        for i, record in enumerate(results):
            percentage = getattr(record, "percentage_present", None)
            logging.debug(f"  Session {i+1}: percentage_present = {percentage} (type: {type(percentage)})")
            if percentage is not None:
                total_attendance += percentage
                count += 1
            else:
                logging.debug(f"  Session {i+1}: Skipping - percentage_present is None")

        logging.info(f"🧮 Calculation summary: total_attendance={total_attendance}, valid_count={count}")

        avg_attendance = round(total_attendance / count, 2) if count > 0 else 0.0
        logging.info(f"📈 Computed average attendance: {avg_attendance}%")

        # --- Prepare response data ---
        response_data = {
            "subject_id": str(subject_id),
            "total_sessions": len(results),
            "average_attendance": avg_attendance,
        }
        logging.info(f"📤 Preparing response: {response_data}")

        # --- Success response ---
        response_content = {
            "status": "success",
            "message": "Average attendance fetched successfully.",
            "data": json.loads(json.dumps(response_data, cls=MongoJSONEncoder)),
        }
        logging.info(f"✅ Success response prepared")
        return JSONResponse(
            status_code=200,
            content=response_content,
        )

    except HTTPException as e:
        logging.error(f"🚨 HTTP Exception: {e}")
        raise e  # re-raise to preserve status code

    except Exception as e:
        logging.exception(f"💥 Unexpected error fetching subject-wise attendance for {subject_id}: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Failed to fetch subject-wise attendance.",
                "error": str(e),
                "data": {},
            },
        )