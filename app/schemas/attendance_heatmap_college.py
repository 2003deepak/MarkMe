from beanie import Document, Indexed
from pydantic import BaseModel, field_validator
from decimal import Decimal
from datetime import date

class AttendanceHeatmapCollege(Document):
    date: Indexed(date, unique=True)  # type: ignore
    average_attendance_percentage: Decimal
    total_sessions: int

    @field_validator("average_attendance_percentage")
    def validate_average_attendance_percentage(cls, v):
        if not (0 <= v <= 100):
            raise ValueError("Average attendance percentage must be between 0 and 100")
        return v

    @field_validator("total_sessions")
    def validate_total_sessions(cls, v):
        if v < 0:
            raise ValueError("Total sessions cannot be negative")
        return v

    class Settings:
        name = "attendance_heatmap_college"
        indexes = [
            "date",                            # Unique index for date
            "average_attendance_percentage"    # Index for sorting/filtering by attendance
        ]