from fastapi import APIRouter, Request
from app.services.student_services.get_student_detail import get_student_detail
from app.services.clerk_services.add_timetable import add_timetable
from app.models.allModel import TimeTableRequest, TimeTableResponse
from app.services.common_services.get_timetable_data import get_timetable_data

router = APIRouter()


@router.post("/timetable")
async def create_timetable_route(
    request_model: TimeTableRequest,
    request: Request
):
    return await add_timetable(request, request_model)


from fastapi import Request
from fastapi.responses import JSONResponse

@router.get("/{program}/{department}/{semester}/{academic_year}")
async def get_timetable(
    request: Request,
    program: str,
    department: str,
    semester: str,
    academic_year: str,
):
    print(f"Received request for /{program}/{department}/{semester}/{academic_year}")
    return await get_timetable_data(request, department, program, semester, academic_year)