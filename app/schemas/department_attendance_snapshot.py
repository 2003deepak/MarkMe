from beanie import Document, Link, Indexed
from pydantic import BaseModel, field_validator
from typing import List
from decimal import Decimal
from datetime import date
from app.schemas.subject import Subject  

class SubjectStats(BaseModel):
    subject: Link[Subject]
    avg_percentage: Decimal
    total_sessions: int

    @field_validator("avg_percentage")
    def validate_avg_percentage(cls, v):
        if not (0 <= v <= 100):
            raise ValueError("Average percentage must be between 0 and 100")
        return v

    @field_validator("total_sessions")
    def validate_total_sessions(cls, v):
        if v < 0:
            raise ValueError("Total sessions cannot be negative")
        return v

class DepartmentAttendanceSnapshot(Document):
    department: str
    year: str
    date: date
    subjects: List[SubjectStats]

    @field_validator("department")
    def validate_department(cls, v):
        valid_departments = ["MCA", "BCA", "CS", "IT", "ENG"]
        if v not in valid_departments:
            raise ValueError(f"Department must be one of {valid_departments}")
        return v

    @field_validator("year")
    def validate_year(cls, v):
        valid_years = ["FYMCA", "SYMCA", "TYMCA", "FYBCA", "SYBCA", "TYBCA"]
        if v not in valid_years:
            raise ValueError(f"Year must be one of {valid_years}")
        return v

    class Settings:
        name = "department_attendance_snapshot"
        indexes = [
            [("department", 1), ("year", 1), ("date", 1)],  # Compound index for queries by department, year, and date
            "date"                                         # Index for date-based queries
        ]