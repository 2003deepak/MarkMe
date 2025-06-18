from fastapi import HTTPException
from app.schemas.student import Student

async def register_student(data: dict):
    required_fields = ["first_name", "last_name", "email", "phone", "dob", "roll_number", "program", "department", "semester", "batch_year", "enrolledDate"]
    for field in required_fields:
        if field not in data:
            raise HTTPException(status_code=400, detail={"status": "fail", "message": f"Missing field: {field}"})

    if "photos" not in data:
        data["photos"] = []

    student_id = f"{data['program']}-{data['department']}-{data['batch_year']}-{data['semester']}-{data['roll_number']}"
    data['student_id'] = student_id
    data['photo_vector'] = [0.0] * 512
    student = Student(**data)
    await student.insert()

    return {
        "status": "success",
        "message": "Student registered successfully",
        "data": {"student_id": student_id}
    }
