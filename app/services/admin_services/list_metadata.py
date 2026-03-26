from fastapi import Request
from fastapi.responses import JSONResponse
from app.schemas.department import Department
from app.schemas.program import Program
from app.core.redis import get_redis_client
import json

async def list_metadata(request: Request) -> JSONResponse:
    try:
        redis = await get_redis_client()
        cached = await redis.get("metadata_listing_v2")
        if cached:
            return JSONResponse(status_code=200, content={"success": True, "data": json.loads(cached), "cached": True})
        
        # Get all programs
        programs = await Program.find_all().to_list()
        # Get all departments with fetched program links
        departments = await Department.find_all(fetch_links=True).to_list()
        
        # Build hierarchy: Program -> Department -> Semesters
        hierarchy = {}
        
        # Initialize programs
        for p in programs:
            hierarchy[p.program_code] = {}
        
        # Map departments to programs
        for d in departments:
            prog = d.program_id
            if isinstance(prog, Program):
                sem_count = prog.duration_years * 2
                semesters = list(range(1, sem_count + 1))
                hierarchy[prog.program_code][d.department_code] = semesters
            
        await redis.set("metadata_listing_v2", json.dumps(hierarchy), ex=3600)
        
        return JSONResponse(status_code=200, content={"success": True, "data": hierarchy, "cached": False})
    except Exception as e:
        import traceback
        return JSONResponse(status_code=500, content={"success": False, "message": str(e), "traceback": traceback.format_exc()})
