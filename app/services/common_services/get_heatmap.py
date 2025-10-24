from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from app.schemas.subject_session_stats import SubjectSessionStats
import json
import logging

from app.services.common_services.get_critical_students import MongoJSONEncoder



async def get_heatmap(
    department: Optional[str] = None,
    program: Optional[str] = None,
    batch_year: Optional[int] = None,
    semester: Optional[int] = None,
    month: Optional[int] = None,
    year: Optional[int] = None
):
    try:
        # Default to current month/year if not provided
        current_date = datetime.now()
        if month is None:
            month = current_date.month
        if year is None:
            year = current_date.year

        # date range for filtering
        start_date = datetime(year, month, 1)
        end_date = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)

        # base filter
        match_filter: Dict[str, Any] = {"date": {"$gte": start_date, "$lt": end_date}}

        # aggregation pipeline
        date_pipeline = [
            {"$match": match_filter},
            {
                "$lookup": {
                    "from": "subjects",
                    "localField": "subject.$id",
                    "foreignField": "_id",
                    "as": "subject_data"
                }
            },
            {"$unwind": "$subject_data"},
        ]

        # dynamic filters
        subject_conditions = {}
        if department:
            subject_conditions["subject_data.department"] = department
        if program:
            subject_conditions["subject_data.program"] = program
        if batch_year:
            subject_conditions["subject_data.batch_year"] = batch_year
        if semester:
            subject_conditions["subject_data.semester"] = semester

        if subject_conditions:
            date_pipeline.append({"$match": subject_conditions})

        # grouping and sorting
        date_pipeline.extend([
            {
                "$group": {
                    "_id": "$date",
                    "average_attendance": {"$avg": "$percentage_present"},
                    "total_sessions": {"$sum": 1}
                }
            },
            {"$sort": {"_id": 1}}
        ])

        # execute aggregation
        logging.info(f"🔥 Running aggregation pipeline with filters: {subject_conditions}")
        date_results = await SubjectSessionStats.aggregate(date_pipeline).to_list(length=None)

        if not date_results:
            response_content = {
                "success": False,
                "message": "No attendance data found for the given filters.",
                "data": {},
            }
            return JSONResponse(status_code=404, content=response_content)

        # format output
        response_data = [
            {
                "date": str(item["_id"].date()),
                "average_attendance": round(item["average_attendance"], 2),
                "total_sessions": item["total_sessions"],
            }
            for item in date_results
        ]

        response_content = {
            "success": True,
            "message": "Average attendance fetched successfully.",
            "data": json.loads(json.dumps(response_data, cls=MongoJSONEncoder)),
        }

        logging.info(f"✅ Success: fetched {len(response_data)} days of heatmap data.")
        return JSONResponse(status_code=200, content=response_content)

    except Exception as e:
        logging.exception(f"💥 Error in get_heatmap: {e}")
        error_content = {
            "success": False,
            "message": "Failed to fetch department heatmap.",
            "error": str(e),
            "data": {},
        }
        return JSONResponse(status_code=500, content=error_content)
