from typing import List, Optional
from fastapi import Request
from fastapi.responses import JSONResponse
from app.schemas.program import Program
from app.models.allModel import CreateProgramRequest, UpdateProgramRequest, ProgramResponse
from app.core.redis import get_redis_client
import json
from bson import ObjectId

async def create_program(request: Request, program_data: CreateProgramRequest) -> JSONResponse:
    try:

        if request.state.user.get("role") != "admin":
        
            return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "message": "You don't have right to create program"
                }
            )

        #exists
        if await Program.find_one(Program.program_code == program_data.program_code):
            return JSONResponse(
                status_code=409,
                content={
                    "success": False,
                    "message": "Program already exists "
                }
            )

        program = Program(
            program_code=program_data.program_code,
            full_name=program_data.full_name,
            duration_years=program_data.duration_years
        )
        await program.insert()
        
        # Invalidate cache
        redis = await get_redis_client()
        await redis.delete("all_programs")
        await redis.delete("metadata_listing_v2")
        
        return JSONResponse(
            status_code=201,
            content={"success": True, "message": "Program created successfully"}
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

async def get_program_by_id(request: Request, id: str) -> JSONResponse:
    try:
        if not ObjectId.is_valid(id):
            return JSONResponse(status_code=400, content={"success": False, "message": "Invalid program ID format"})

        program = await Program.get(id)
        if not program:
            return JSONResponse(status_code=404, content={"success": False, "message": "Program not found"})
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": {
                    "id": str(program.id),
                    "program_code": program.program_code,
                    "full_name": program.full_name,
                    "duration_years": program.duration_years,
                    "is_active": program.is_active
                }
            }
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

async def update_program(request: Request, id: str, update_data: UpdateProgramRequest) -> JSONResponse:
    try:
        if not ObjectId.is_valid(id):
            return JSONResponse(status_code=400, content={"success": False, "message": "Invalid program ID format"})

        program = await Program.get(id)
        if not program:
            return JSONResponse(status_code=404, content={"success": False, "message": "Program not found"})
        
        update_dict = update_data.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            setattr(program, key, value)
        
        await program.save()
        
        # Invalidate cache
        redis = await get_redis_client()
        await redis.delete("all_programs")
        await redis.delete("metadata_listing_v2")
        
        return JSONResponse(status_code=200, content={"success": True, "message": "Program updated successfully"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})


async def list_all_programs(request: Request) -> JSONResponse:
    try:
        redis = await get_redis_client()
        cached = await redis.get("all_programs")
        if cached:
            return JSONResponse(status_code=200, content={"success": True, "data": json.loads(cached), "cached": True})
        
        programs = await Program.find_all().to_list()
        data = [
            {
                "id": str(p.id),
                "program_code": p.program_code,
                "full_name": p.full_name,
                "duration_years": p.duration_years,
                "is_active": p.is_active
            } for p in programs
        ]
        
        await redis.set("all_programs", json.dumps(data), ex=3600) # Cache for 1 hour
        
        return JSONResponse(status_code=200, content={"success": True, "data": data, "cached": False})
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})
