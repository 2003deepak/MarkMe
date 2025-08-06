from beanie import Document, Link, Indexed
from pydantic import BaseModel, field_validator
from typing import Optional
from decimal import Decimal
from datetime import date
from app.schemas.subject import Subject
from app.schemas.attendance import Attendance


class SubjectSessionStats(Document):
    session_id: Link[Attendance]
    subject: Link[Subject]
    date: date
    component_type: str
    present_count: int
    absent_count: int
    percentage_present: Decimal

    @field_validator("component_type")
    def validate_component_type(cls, v):
        valid_types = ["Lecture", "Tutorial", "Lab", "Seminar"]
        if v not in valid_types:
            raise ValueError(f"Component type must be one of {valid_types}")
        return v

    @field_validator("present_count")
    def validate_present_count(cls, v):
        if v < 0:
            raise ValueError("Present count cannot be negative")
        return v

    @field_validator("absent_count")
    def validate_absent_count(cls, v):
        if v < 0:
            raise ValueError("Absent count cannot be negative")
        return v

    @field_validator("percentage_present")
    def validate_percentage_present(cls, v):
        if not (0 <= v <= 100):
            raise ValueError("Percentage present must be between 0 and 100")
        return v

    class Settings:
        name = "subject_session_stats"
        indexes = [
            [("subject", 1), ("date", 1)],  # Compound index for queries by subject and date
            "session_id",                   # Unique index for session_id
            "percentage_present"           # Index for sorting/filtering by attendance percentage
        ]