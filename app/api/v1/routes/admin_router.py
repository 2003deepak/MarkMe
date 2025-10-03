from fastapi import APIRouter, Request, Path
from app.services.admin_services.create_clerk import create_clerk
from app.services.admin_services.get_clerk import get_clerk, get_clerk_by_id
from app.services.admin_services.delete_clerk import delete_clerk
from app.models.allModel import CreateClerkRequest

router = APIRouter()

# Create Clerk
@router.post("/clerk")
async def create_clerk_route(
    request_model: CreateClerkRequest,
    request: Request
):
    return await create_clerk(request, request_model)


# Get clerks by department
@router.get("/clerk/department/{department}")
async def get_clerk_by_department_route(
    request: Request = None,
    department: str = Path(..., description="Department to fetch clerks for"),
):
    return await get_clerk(request, department)


# Get clerk by email
@router.get("/clerk/{email_id}")
async def get_clerk_by_id_route(
    request: Request ,
    email_id: str = Path(..., description="Email ID"),
):
    return await get_clerk_by_id(request,email_id)


# Delete clerk by email
@router.delete("/clerk/{email_id}")
async def delete_clerk_route(
    email_id: str = Path(..., description="Email ID"),
    request: Request = None
):
    return await delete_clerk(request,email_id)
