from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, field_validator
from typing import List, Dict
from bson import ObjectId
import re
from datetime import datetime




# Pydantic model for Session
class Session(BaseModel):
    start_time: str = Field(...)  # Format: "HH:MM"
    end_time: str = Field(...)    # Format: "HH:MM"
    subject: str              # Reference to Subject ID
    teacher: str              # Reference to Teacher ID

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time_format(cls, v):
        if not isinstance(v, str) or v.count(":") != 1:
            raise ValueError("Time must be in HH:MM format")
        try:
            hours, minutes = map(int, v.split(":"))
            if not (0 <= hours <= 23 and 0 <= minutes <= 59):
                raise ValueError("Invalid time value")
        except ValueError:
            raise ValueError("Invalid time format")
        return v

    @field_validator("end_time")
    @classmethod
    def validate_time_order(cls, end_time, values):
        if "start_time" in values:
            start = datetime.strptime(values["start_time"], "%H:%M")
            end = datetime.strptime(end_time, "%H:%M")
            if end <= start:
                raise ValueError("End time must be after start time")
        return end_time
    
    @field_validator("subject", "teacher")
    @classmethod
    def validate_object_id(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId format")
        return v

    
    
# Pydantic model for Timetable
class Timetable(BaseModel):
    academic_year: str = Field(...)
    department: str = Field(...)
    program: str = Field(...)
    semester: str = Field(...)
    schedule: Dict[str, List[Session]] = {
        "Monday": [], "Tuesday": [], "Wednesday": [], 
        "Thursday": [], "Friday": [], "Saturday": [], "Sunday": []
    }

    @field_validator("academic_year")
    @classmethod
    def validate_academic_year(cls, v):
        if not re.match(r"^\d{4}-\d{2}$", v):
            raise ValueError("Academic year must be in YYYY-YY format")
        return v


 
# Repository for Timetable operations
class TimetableRepository:
    def __init__(self, client: AsyncIOMotorClient, db_name: str):
        self.db = client[db_name]
        self.timetables = self.db["timetables"]
        self.subjects = self.db["subjects"]
        self.teachers = self.db["teachers"]

    async def ensure_indexes(self):
        """Create necessary indexes."""
        await self.timetables.create_index([("academic_year", 1)])
        await self.timetables.create_index([("department", 1)])
        await self.timetables.create_index([("program", 1)])
        await self.timetables.create_index(
            [("academic_year", 1), ("department", 1), ("program", 1)],
            unique=True
        )

    async def validate_references(self, session: Session):
        """Validate subject and teacher references exist."""
        subject_id = ObjectId(session.subject.id)
        teacher_id = ObjectId(session.teacher.id)
        if not await self.subjects.find_one({"_id": subject_id}):
            raise ValueError(f"Subject with ID {session.subject.id} does not exist")
        if not await self.teachers.find_one({"_id": teacher_id}):
            raise ValueError(f"Teacher with ID {session.teacher.id} does not exist")



   