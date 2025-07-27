from beanie import Document, Link, Indexed
from pydantic import BaseModel, field_validator, computed_field
from typing import List
from decimal import Decimal
from app.schemas.student import Student
from app.schemas.subject import Subject

class StudentAttendance(BaseModel):
    student: Link[Student]
    roll: str
    attended: int
    total: int

    @field_validator("attended")
    def validate_attended(cls, v):
        if v < 0:
            raise ValueError("Attended count cannot be negative")
        return v

    @field_validator("total")
    def validate_total(cls, v):
        if v < 0:
            raise ValueError("Total sessions cannot be negative")
        return v

    @field_validator("attended")
    def validate_attended_less_than_total(cls, v, values):
        if "total" in values and v > values["total"]:
            raise ValueError("Attended count cannot exceed total sessions")
        return v

    @field_validator("roll")
    def validate_roll(cls, v):
        if not v.startswith("MCA"):
            raise ValueError("Roll number must start with 'MCA'")
        return v

    @computed_field
    @property
    def percentage(self) -> Decimal:
        if self.total == 0:
            return Decimal("0.0")
        return Decimal((self.attended / self.total) * 100).quantize(Decimal("0.1"))

class SubjectAttendanceRoster(Document):
    subject: Link[Subject]
    students: List[StudentAttendance]

    class Settings:
        name = "subject_attendance_roster"
        indexes = [
            "subject",                    # Index for queries by subject
            [("subject", 1), ("students.student", 1)],  # Compound index for subject and student queries
        ]