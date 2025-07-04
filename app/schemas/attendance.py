from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

class Attendance(BaseModel):
    timetable_id: ObjectId
    date: datetime
    day: str
    slot_index: int
    subject: ObjectId
    component_type: str
    students: Optional[str] = None

    @field_validator("day")
    @classmethod
    def validate_day(cls, v):
        valid_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        if v not in valid_days:
            raise ValueError(f"Day must be one of: {valid_days}")
        return v

    @field_validator("slot_index")
    @classmethod
    def validate_slot_index(cls, v):
        if v < 0:
            raise ValueError("slotIndex must be at least 0")
        return v

    @field_validator("timetable_id", "subject")
    @classmethod
    def validate_object_id(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId format")
        return ObjectId(v)  # Convert to ObjectId

    class Config:
        arbitrary_types_allowed = True  # Allow ObjectId type

class AttendanceRepository:
    def __init__(self, client: AsyncIOMotorClient, db_name: str):
        self.db = client[db_name]
        self.collection = self.db["attendances"]

    async def ensure_indexes(self):
        await self.collection.create_index(
            [("timetable_id", 1), ("date", 1), ("day", 1), ("slot_index", 1)],
            unique=True
        )