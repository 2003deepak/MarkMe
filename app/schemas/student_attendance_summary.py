from pydantic import BaseModel, Field, field_validator
from typing import List
from motor.motor_asyncio import AsyncIOMotorClient
import pymongo


class StudentAttendanceSummary(BaseModel):
    student_id: str
    subject_id: str
    total_classes: int
    attended: int
    percentage: float
    sessions_present: List[str]

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


class StudentAttendanceSummaryRepository:
    def __init__(self, client: AsyncIOMotorClient, db_name: str):
        self.db = client[db_name]
        self.collection = self.db["student_attendance_summary"]

    async def ensure_indexes(self):
        await self.collection.create_index(
            [("student_id", pymongo.ASCENDING), ("subject_id", pymongo.ASCENDING)],
            unique=True,
            name="student_subject_idx"
        )