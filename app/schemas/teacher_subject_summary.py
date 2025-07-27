from beanie import Document, Link, Indexed
from pydantic import BaseModel, field_validator
from typing import Optional
from decimal import Decimal
from app.schemas.teacher import Teacher
from app.schemas.subject import Subject


class TeacherSubjectSummary(Document):
    teacher: Link[Teacher]
    subject: Link[Subject]
    total_sessions_conducted: int
    average_attendance_percentage: Decimal
    defaulter_count: int
    at_risk_count: int
    top_performer_count: int

    @field_validator("total_sessions_conducted")
    def validate_total_sessions(cls, v):
        if v < 0:
            raise ValueError("Total sessions conducted cannot be negative")
        return v

    @field_validator("average_attendance_percentage")
    def validate_attendance_percentage(cls, v):
        if not (0 <= v <= 100):
            raise ValueError("Average attendance percentage must be between 0 and 100")
        return v

    @field_validator("defaulter_count")
    def validate_defaulter_count(cls, v):
        if v < 0:
            raise ValueError("Defaulter count cannot be negative")
        return v

    @field_validator("at_risk_count")
    def validate_at_risk_count(cls, v):
        if v < 0:
            raise ValueError("At-risk count cannot be negative")
        return v

    @field_validator("top_performer_count")
    def validate_top_performer_count(cls, v):
        if v < 0:
            raise ValueError("Top performer count cannot be negative")
        return v

    class Settings:
        name = "teacher_subject_summary"
        indexes = [
            [("teacher", 1), ("subject", 1)],  # Compound index for queries by teacher and subject
            "average_attendance_percentage"    # Index for sorting/filtering by attendance
        ]