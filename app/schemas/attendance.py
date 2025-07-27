from pydantic import Field, field_validator
from typing import Optional
from datetime import datetime
from beanie import Document, Indexed, Link
from app.schemas.timetable import Timetable  
from app.schemas.subject import Subject  

class Attendance(Document):
    timetable_id: Link[Timetable] 
    date: Indexed(datetime)  # type: ignore
    day: Indexed(str)  # type: ignore
    slot_index: Indexed(int)  # type: ignore
    subject: Link[Subject] 
    component_type: str
    students: Optional[str] = None
    created_at: Indexed(datetime) = Field(default_factory=datetime.utcnow)  # type: ignore
    updated_at: Indexed(datetime) = Field(default_factory=datetime.utcnow)  # type: ignore

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

    class Settings:
        name = "attendances"
        indexes = [
            [("timetable_id", 1), ("date", 1), ("day", 1), ("slot_index", 1)],
        ]

        async def pre_save(self) -> None:
            self.updated_at = datetime.utcnow()
            if not self.created_at:
                self.created_at = self.updated_at

    class Config:
        arbitrary_types_allowed = True
