from fastapi import Request
from fastapi.responses import JSONResponse
from app.schemas.department import Department
from app.schemas.program import Program
from app.core.redis import get_redis_client
import json

async def list_metadata(request: Request) -> JSONResponse:
    try:
        redis = await get_redis_client()
        cached = await redis.get("metadata_listing")
        if cached:
            return JSONResponse(status_code=200, content={"success": True, "data": json.loads(cached), "cached": True})
        
        # Get distinct departments
        departments = await Department.find_all().to_list()
        dept_names = sorted(list(set(d.department_code for d in departments)))
        
        # Get distinct programs
        programs = await Program.find_all().to_list()
        program_names = sorted(list(set(p.program_code for p in programs)))
        
        # Semesters are typically 1-8
        semesters = list(range(1, 9))
        
        result = {
            "departments": dept_names,
            "programs": program_names,
            "semesters": semesters
        }
        
        await redis.set("metadata_listing", json.dumps(result), ex=3600)
        
        return JSONResponse(status_code=200, content={"success": True, "data": result, "cached": False})
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})
