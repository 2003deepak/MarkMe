from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from app.schemas.subject_session_stats import SubjectSessionStats
from app.schemas.subject import Subject
import json  # For pretty printing if needed


async def get_attendance_summary_department(
    department_name: str,
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

    # print(f"Query params: dept={department_name},  month={month}, year={year}")
    # print(f"Date range: {start_date} to {end_date}")

    # base query
    match_filter: Dict[str, Any] = {
        "date": {"$gte": start_date, "$lt": end_date}
    }

    # DEBUG: Check docs in date range
    date_pipeline = [{"$match": match_filter}]
    date_results = await SubjectSessionStats.aggregate(date_pipeline).to_list(length=None)
    # print(f"Docs in date range: {len(date_results)}")
    # if date_results:
    #     # print("Sample date docs:", json.dumps(date_results[:-1], default=str, indent=2))

    if len(date_results) == 0:
        # Still raise, but now with more info
       
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "message": "No attendance records found for {}/{}".format(month, year),
            }
        )


    # DEBUG: Lookup and inspect subject details
    lookup_pipeline = [
        {"$match": match_filter},
        {
            "$lookup": {
                "from": "subjects",
                "let": {"subj_id": "$subject.$id"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {"$eq": ["$_id", "$$subj_id"]}
                        }
                    }
                ],
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
                "semester": "$subject_doc.semester",
                "date": 1,
                "percentage_present": 1,
                "present_count": 1,
                "absent_count": 1
            }
        }
    ]
    lookup_results = await SubjectSessionStats.aggregate(lookup_pipeline).to_list(length=None)
    # print(f"Docs after lookup & unwind: {len(lookup_results)}")
    # if lookup_results:
    #     print("Sample subject details:")
    #     for doc in lookup_results[:-1]:  # First 3
    #         print(json.dumps(doc, default=str, indent=2))

    # Now build the main pipeline
    pipeline = [
        {"$match": match_filter},
        {
            "$lookup": {
                "from": "subjects",
                "let": {"subj_id": "$subject.$id"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {"$eq": ["$_id", "$$subj_id"]}
                        }
                    }
                ],
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

   
    # Now define group stage
    group_keys = {
        "program": "$subject_doc.program",
        "sem": "$subject_doc.semester"
    }
  
    group_stage = {
        "$group": {
            **{"_id": group_keys},
            "total_present": {"$sum": "$present_count"},
            "total_absent": {"$sum": "$absent_count"},
            "program": {"$first": "$subject_doc.program"},
            "sem": {"$first": "$subject_doc.semester"},
        }
    }

    # Project stage
    project_fields = {
        "_id": 0,
        "program": 1,
        "sem": 1,
        "avg_attendance": {
            "$round": [
                {
                    "$multiply": [
                        {
                            "$divide": [
                                "$total_present",
                                {
                                    "$add": ["$total_present", "$total_absent"]
                                }
                            ]
                        },
                        100
                    ]
                },
                2
            ]
        },
    }
   

    project_stage = {"$project": project_fields}

    pipeline.extend([group_stage, project_stage])

    # # DEBUG: Print the pipeline
    # print("Aggregation pipeline:")
    # for stage in pipeline:
    #     print(json.dumps(stage, default=str, indent=2))

    results = await SubjectSessionStats.aggregate(pipeline).to_list(length=None)
    
    # print(f"Final results: {len(results)}")
    # if results:
    #     print(json.dumps(results, default=str, indent=2))

    if not results:

        return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "message": "No attendance records found for department '{department_name}' in {month}/{year}.",

                }
            )
        
        

    # Build response: list of summaries
    summaries = []
    for r in results:
        entry = {
            "department": department_name,
            "month": month,
            "year": year,
            "program": r["program"],
            "sem": r["sem"],
            "avg_attendance": r["avg_attendance"]
        }
        summaries.append(entry)
        
        
        
    return JSONResponse(
                status_code=201,
                content={
                    "success": True,
                    "message": "Records Found Successfully",
                    "data" : {
                        "department": department_name,
                        "month": month,
                        "year": year,
                        "program_semesters": summaries
                        
                    }

                }
            )

    return {
        "department": department_name,
        "month": month,
        "year": year,
        "program_semesters": summaries
    }