from fastapi import HTTPException
from pydantic import BaseModel
from app.core.redis import redis_client
from bson import ObjectId, DBRef
import json
import logging
from datetime import datetime
from fastapi.encoders import jsonable_encoder
from bson import ObjectId
from typing import Dict, Any, List, Optional
from app.schemas.student_attendance_summary import StudentAttendanceSummary
from app.schemas.student import Student
from app.schemas.session import Session
from app.schemas.subject import Subject
from app.schemas.attendance import Attendance

# JSON encoder to handle ObjectId and datetime
class MongoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

async def get_student_attendance_summary(student_id: str, user_data: dict) -> Dict[str, Any]:
   
    print(f"📊 Request for student attendance summary: {student_id}")
    print(f"🧾 user_data = {user_data}")  # 🔍 Inspect structure
    

    user_role = user_data["role"]

    
    # 1. ROLE-BASED AUTHORIZATION CHECK
    allowed_roles = {"student", "clerk", "admin", "teacher"}
    
    if user_role not in allowed_roles:
        print(f"❌ Access denied: Role '{user_role}' not in allowed roles {allowed_roles}")
        raise HTTPException(
            status_code=403,
            detail={
                "status": "fail", 
                "message": f"Access denied. Role '{user_role}' not authorized to view attendance summaries"
            }
        )
    
    # Additional permission check for students
    # if user_role == "student" and user_id != student_id:
    #     print(f"❌ Access denied: Student {user_id} trying to access {student_id}'s data")
    #     raise HTTPException(
    #         status_code=403,
    #         detail={
    #             "status": "fail",
    #             "message": "Students can only view their own attendance summary"
    #         }
    #     )
    
    print(f"✅ Authorization passed for {user_role}")
    
    # 2. CACHING - Try to get from cache first
    cache_key = f"student_attendance_summary:{student_id}:{user_role}"
    cached_data = await redis_client.get(cache_key)
    
    if cached_data:
        print(f"✅ Found cached data for {cache_key}")
        try:
            return {
                "status": "success",
                "data": json.loads(cached_data),
                "source": "cache"
            }
        except json.JSONDecodeError as e:
            print(f"⚠️ Cache corruption detected for {cache_key}: {e}")
            await redis_client.delete(cache_key)
    
    print(f"ℹ️ Cache miss for {cache_key} — fetching from database...")
    
    # 3. FETCH OR CALCULATE DATA FROM DATABASE
    try:
        # Verify student exists
        student = await Student.get(student_id)
        if not student:
            print(f"❌ Student {student_id} not found")
            raise HTTPException(
                status_code=404,
                detail={"status": "fail", "message": "Student not found"}
            )
        
        print(f"✅ Student {student.first_name} ({student.email}) verified")
        
        # Get attendance summaries using Beanie's project method
        summaries = await StudentAttendanceSummary.find(
            StudentAttendanceSummary.student.id == ObjectId(student_id),
            fetch_links=True
        ).to_list()

        
        print(f"📊 Found {len(summaries)} existing summary records")
        
     
        
        result = []
        for summary in summaries:
            result.append({
                "subject_name": summary.subject.subject_name if summary.subject else "Unknown Subject",
                "total_classes": summary.total_classes,
                "attended": summary.attended,
                "percentage": summary.percentage
            })

        # cache result
        await redis_client.setex(cache_key, 1800, json.dumps(result))

        return {
            "status": "success",
            "data": result,
            "source": "database"
        }

    
        
    except HTTPException:
        print("❌ HTTPException raised during processing")
        raise
    except Exception as e:
        print(f"💥 Unhandled exception in get_student_attendance_summary: {str(e)}")
        logging.error(f"Error processing attendance summary for {student_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "message": "Failed to fetch attendance summary due to server error"
            }
        )


