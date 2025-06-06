from beanie import Document, Indexed
from pydantic import Field, field_validator
from typing import List
from datetime import datetime

class Attendance(Document):
    timetable_id: Indexed(str) = Field(..., alias="timetableId")  # ObjectId as string
    date: Indexed(datetime)
    day: str
    slot_index: int = Field(..., alias="slotIndex")
    subject_id: str = Field(..., alias="subjectId")  # ObjectId as string
    teacher_id: str = Field(..., alias="teacherId")  # ObjectId as string
    present_students: List[str] = Field(default_factory=list, alias="presentStudents")  # ObjectId as string

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
        use_state_management = True
