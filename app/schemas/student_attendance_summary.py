from pydantic import BaseModel, Field, field_validator
from typing import List
from beanie import Document, Indexed, Link
from datetime import datetime
from bson import ObjectId
from app.schemas.subject import Subject  
from app.schemas.student import Student
from app.schemas.attendance import Attendance

class StudentAttendanceSummary(Document):
    student_id: Link[Student]  # type: ignore  # Keeping as string for now, consider Link[Student] if needed
    subject_id: Link[Subject]  # Changed to Link for subject reference
    total_classes: int
    attended: int
    percentage: float
    sessions_present: List[Link[Attendance]]  
    created_at: Indexed(datetime) = datetime.utcnow()  # type: ignore
    updated_at: Indexed(datetime) = datetime.utcnow()  # type: ignore

    @field_validator("total_classes", "attended")
    @classmethod
    def validate_positive(cls, v, field):
        if v < 0:
            raise ValueError(f"{field.name} must be non-negative")
        return v

    @field_validator("percentage")
    @classmethod
    def validate_percentage(cls, v):
        if v < 0 or v > 100:
            raise ValueError("Percentage must be between 0 and 100")
        return round(v, 2)

   

    class Settings:
        name = "student_attendance_summary"
        indexes = [
            [("student_id", 1), ("subject_id", 1)],
        ]

        # Automatically update updated_at timestamp on save
        async def pre_save(self) -> None:
            self.updated_at = datetime.utcnow()
            if not self.created_at:
                self.created_at = self.updated_at