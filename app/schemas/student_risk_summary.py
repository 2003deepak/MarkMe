from beanie import Document, Link, Indexed
from pydantic import BaseModel, field_validator
from typing import List
from decimal import Decimal
from app.schemas.student import Student
from app.schemas.subject import Subject

class DefaulterSubject(BaseModel):
    subject: Link[Subject]
    percentage: Decimal

    @field_validator("percentage")
    def validate_percentage(cls, v):
        if not (0 <= v <= 100):
            raise ValueError("Percentage must be between 0 and 100")
        return v

class StudentRiskSummary(Document):
    student: Link[Student]
    department: str
    sem: int
    total_subjects: int
    defaulter_subjects: List[DefaulterSubject]
    defaulter_count: int
    average_percentage: Decimal

    


    @field_validator("total_subjects")
    def validate_total_subjects(cls, v):
        if v < 0:
            raise ValueError("Total subjects cannot be negative")
        return v

    @field_validator("defaulter_count")
    def validate_defaulter_count(cls, v, values):
        if "defaulter_subjects" in values and v != len(values["defaulter_subjects"]):
            raise ValueError("Defaulter count must match the number of defaulter subjects")
        if v < 0:
            raise ValueError("Defaulter count cannot be negative")
        return v

    @field_validator("average_percentage")
    def validate_average_percentage(cls, v):
        if not (0 <= v <= 100):
            raise ValueError("Average percentage must be between 0 and 100")
        return v

    class Settings:
        name = "student_risk_summary"
        indexes = [
            "student",                        # Index for queries by student
            [("department", 1), ("year", 1)], # Compound index for department and year queries
            "average_percentage"              # Index for sorting/filtering by average percentage
        ]