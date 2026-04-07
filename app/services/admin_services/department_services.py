from typing import List, Optional
from fastapi import Request,Depends
from fastapi.responses import JSONResponse
from app.schemas.department import Department
from app.schemas.program import Program
from app.models.allModel import CreateDepartmentRequest, UpdateDepartmentRequest, DepartmentResponse
from app.core.redis import get_redis_client
import json
from beanie import Link
from bson import ObjectId
from app.core.redis import get_redis_client

async def create_department(request: Request, dept_data: CreateDepartmentRequest) -> JSONResponse:
    try:

        if request.state.user.get("role") != "admin":
        
            return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "message": "You don't have right to create department"
                }
            )

        #exists
        if await Department.find_one(Department.department_code == dept_data.department_code and Department.program_id == dept_data.program_code):
            return JSONResponse(
                status_code=409,
                content={
                    "success": False,
                    "message": "Department already exists"
                }
            )


        # Find program by ID or code
        program = None
        if ObjectId.is_valid(dept_data.program_code):
            program = await Program.get(dept_data.program_code)
        
        if not program:
            program = await Program.find_one(Program.program_code == dept_data.program_code)

        if not program:
            return JSONResponse(status_code=404, content={"success": False, "message": "Program not found"})
        
        department = Department(
            full_name=dept_data.full_name,
            department_code=dept_data.department_code,
            program_id=program
        )
        await department.insert()
        
        # Invalidate cache
        redis = await get_redis_client()
        await redis.delete("all_departments")
        await redis.delete("metadata_listing_v2")
        
        return JSONResponse(
            status_code=201,
            content={"success": True, "message": "Department created successfully"}
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

async def get_department_by_id(request: Request, id: str) -> JSONResponse:
    try:
        if not ObjectId.is_valid(id):
            return JSONResponse(status_code=400, content={"success": False, "message": "Invalid department ID format"})

        department = await Department.get(id, fetch_links=True)
        if not department:
            return JSONResponse(status_code=404, content={"success": False, "message": "Department not found"})
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": {
                    "id": str(department.id),
                    "full_name": department.full_name,
                    "department_code": department.department_code,
                    "program_id": str(department.program_id.id) if department.program_id else None,
                    "is_active": department.is_active
                }
            }
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

async def update_department(request: Request, id: str, update_data: UpdateDepartmentRequest) -> JSONResponse:
    try:
        if not ObjectId.is_valid(id):
            return JSONResponse(status_code=400, content={"success": False, "message": "Invalid department ID format"})

        department = await Department.get(id)
        if not department:
            return JSONResponse(status_code=404, content={"success": False, "message": "Department not found"})
        
        update_dict = update_data.model_dump(exclude_unset=True)
        
        if "program_code" in update_dict:
            program_input = update_dict["program_code"]
            program = None
            if ObjectId.is_valid(program_input):
                program = await Program.get(program_input)
            
            if not program:
                program = await Program.find_one(Program.program_code == program_input)

            if not program:
                return JSONResponse(status_code=404, content={"success": False, "message": "New Program not found"})
            department.program_id = program
            del update_dict["program_code"]

        for key, value in update_dict.items():
            setattr(department, key, value)
        
        await department.save()
        
        # Invalidate cache
        redis = await get_redis_client()
        await redis.delete("all_departments")
        await redis.delete("metadata_listing_v2")
        
        return JSONResponse(status_code=200, content={"success": True, "message": "Department updated successfully"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

async def list_all_departments(request: Request) -> JSONResponse:
    try:
        redis = await get_redis_client()
        cached = await redis.get("all_departments")
        if cached:
            return JSONResponse(status_code=200, content={"success": True, "data": json.loads(cached), "cached": True})
        
        departments = await Department.find_all(fetch_links=True).to_list()
        data = [
            {
                "id": str(d.id),
                "full_name": d.full_name,
                "department_code": d.department_code,
                "program_id": str(d.program_id.id) if d.program_id else None,
                "is_active": d.is_active
            } for d in departments
        ]
        
        await redis.set("all_departments", json.dumps(data), ex=3600)
        
        return JSONResponse(status_code=200, content={"success": True, "data": data, "cached": False})
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})
