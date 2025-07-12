from fastapi import HTTPException
from app.core.database import get_db
from app.core.redis import redis_client
import json

async def get_all_teachers(user_data):
    if user_data["role"] != "clerk":
        raise HTTPException(status_code=403, detail="Only clerks can access this route")
    
    department = user_data.get("department")
    if not department:
        raise HTTPException(status_code=400, detail="Department not found in user data")
    
    cache_key = f"teachers:{department}"
    cached_teachers = await redis_client.get(cache_key)

    if cached_teachers:
        return {"status": "success", "data": json.loads(cached_teachers)}

    db = get_db()
    teachers_cursor = db.teachers.find(
        {"department": department},
        {"password": 0, "created_at": 0, "updated_at": 0}
    )

    teachers = []
    async for teacher in teachers_cursor:
        teacher["_id"] = str(teacher["_id"])
        teachers.append(teacher)

    await redis_client.setex(cache_key, 3600, json.dumps(teachers))  # 1 hour cache

    return {"status": "success", "data": teachers}
