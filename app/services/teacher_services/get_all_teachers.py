from fastapi import HTTPException
from app.core.database import get_db
from app.core.redis import redis_client
import json

async def get_all_teachers(user_data):
    if user_data["role"] != "clerk":
        raise HTTPException(status_code=403, detail="Only clerks can access this route")
    
    db = get_db()
    email = user_data["email"]

    # Use find_one to get the clerk's department only
    clerk = await db.clerks.find_one(
        {"email": email},
        {"department": 1} 
    )

    if clerk is None or "department" not in clerk:
        raise HTTPException(status_code=400, detail="Clerk department not found")

    department = clerk["department"]
    cache_key = f"teachers:{department}"

    # Try fetching from Redis
    cached_teachers = await redis_client.get(cache_key)
    if cached_teachers:
        return {"status": "success", "data": json.loads(cached_teachers)}

    # Fetch teachers from MongoDB, including only JSON-serializable fields
    teachers_cursor = db.teachers.find(
        {"department": department},
        {
            "teacher_id": 1,
            "first_name": 1,
            "middle_name": 1,
            "last_name": 1,
            "profile_picture": 1,
            "email": 1,
            "mobile_number": 1,
            "department": 1,
            "phone": 1
        }  
    )

    teachers = []
    async for teacher in teachers_cursor:
        teacher.pop("_id", None)
        teachers.append(teacher)

    # Cache result in Redis for 1 hour
    await redis_client.setex(cache_key, 3600, json.dumps(teachers))

    return {"status": "success", "data": teachers}