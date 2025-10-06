from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import HTTPException
from app.schemas.subject_session_stats import SubjectSessionStats
from app.schemas.subject import Subject
import json  # For pretty printing if needed


async def get_attendance_summary_department(
    department_name: str,
    program: Optional[str],
    month: int,
    year: int
) -> Dict[str, Any]:
    """
    Core logic for department/program-wise attendance stats.
    """

    # date range for filtering
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1)
    else:
        end_date = datetime(year, month + 1, 1)

    print(f"Query params: dept={department_name}, program={program}, month={month}, year={year}")
    print(f"Date range: {start_date} to {end_date}")

    # base query
    match_filter: Dict[str, Any] = {
        "date": {"$gte": start_date, "$lt": end_date}
    }

    # DEBUG: Check docs in date range
    date_pipeline = [{"$match": match_filter}]
    date_results = await SubjectSessionStats.aggregate(date_pipeline).to_list(length=None)
    print(f"Docs in date range: {len(date_results)}")
    if date_results:
        print("Sample date docs:", json.dumps(date_results[:2], default=str, indent=2))

    if len(date_results) == 0:
        # Still raise, but now with more info
        raise HTTPException(status_code=404, detail=f"No attendance records found for {month}/{year}")

    # DEBUG: Lookup and inspect subject details
    lookup_pipeline = [
        {"$match": match_filter},
        {
            "$lookup": {
                "from": "subjects",
                "localField": "subject",
                "foreignField": "_id",
                "as": "subject_doc"
            }
        },
        {"$unwind": "$subject_doc"},
        {
            "$project": {
                "subject_id": "$subject_doc._id",
                "subject_name": "$subject_doc.name",
                "department": "$subject_doc.department",
                "program": "$subject_doc.program",
                "date": 1,
                "percentage_present": 1,
                "present_count": 1,
                "absent_count": 1
            }
        }
    ]
    lookup_results = await SubjectSessionStats.aggregate(lookup_pipeline).to_list(length=None)
    print(f"Docs after lookup & unwind: {len(lookup_results)}")
    if lookup_results:
        print("Sample subject details:")
        for doc in lookup_results[:3]:  # First 3
            print(json.dumps(doc, default=str, indent=2))

    # Now build the main pipeline
    pipeline = [
        {"$match": match_filter},
        {
            "$lookup": {
                "from": "subjects",
                "localField": "subject",
                "foreignField": "_id",
                "as": "subject_doc"
            }
        },
        {"$unwind": "$subject_doc"},
        {
            "$match": {
                "subject_doc.department": department_name
            }
        }
    ]

    # Add program filter if provided (insert before the department match for clarity, but order doesn't matter)
    if program:
        pipeline.insert(-1, {  # Insert before department match
            "$match": {
                "subject_doc.program": program
            }
        })

    pipeline.extend([
        {"$group": {
            "_id": "$subject_doc._id",
            "subject_name": {"$first": "$subject_doc.name"},
            "avg_attendance": {"$avg": "$percentage_present"},
            "total_sessions": {"$sum": 1},
            "total_present": {"$sum": "$present_count"},
            "total_absent": {"$sum": "$absent_count"},
        }},
        {"$project": {
            "_id": 0,
            "subject_id": {"$toString": "$_id"},
            "subject_name": 1,
            "avg_attendance": {"$round": ["$avg_attendance", 2]},
            "total_sessions": 1,
            "total_present": 1,
            "total_absent": 1,
        }}
    ])

    # DEBUG: Print the pipeline
    print("Aggregation pipeline:")
    for stage in pipeline:
        print(json.dumps(stage, default=str, indent=2))

    results = await SubjectSessionStats.aggregate(pipeline).to_list(length=None)
    
    print(f"Final results: {len(results)}")
    if results:
        print(json.dumps(results, default=str, indent=2))

    if not results:
        # Provide more helpful error
        raise HTTPException(
            status_code=404, 
            detail=f"No attendance records found for department '{department_name}'" + 
                   (f", program '{program}'" if program else "") + 
                   f" in {month}/{year}. Check the debug logs above for data availability."
        )

    # Build response
    return {
        "department": department_name,
        "program": program,
        "month": month,
        "year": year,
        "subjects": results
    }