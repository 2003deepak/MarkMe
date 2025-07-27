from pydantic import BaseModel, Field, field_validator
from typing import List, Dict
from beanie import Document, Indexed
from bson import ObjectId, DBRef
import re
from datetime import datetime
from fastapi import HTTPException
import logging

# Pydantic model for Session
class Session(BaseModel):
    start_time: str = Field(...)  # Format: "HH:MM"
    end_time: str = Field(...)    # Format: "HH:MM"
    subject: DBRef = Field(...)   # Changed to DBRef for subject references

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
        if "start_time" in values.data:
            start = datetime.strptime(values.data["start_time"], "%H:%M")
            end = datetime.strptime(end_time, "%H:%M")
            if end <= start:
                raise ValueError("End time must be after start time")
        return end_time

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, v):
        if not isinstance(v, DBRef) or v.collection != "subject" or not isinstance(v.id, ObjectId):
            raise ValueError("Subject must be a valid DBRef with collection 'subject' and ObjectId")
        return v

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str, DBRef: lambda dbref: {"$ref": dbref.collection, "$id": str(dbref.id)}}

# Beanie Document model for Timetable
class Timetable(Document):
    academic_year: Indexed(str)  # type: ignore
    department: Indexed(str)  # type: ignore
    program: Indexed(str)  # type: ignore
    semester: str
    schedule: Dict[str, List[Session]] = {
        "Monday": [], "Tuesday": [], "Wednesday": [],
        "Thursday": [], "Friday": [], "Saturday": [], "Sunday": []
    }
    created_at: Indexed(datetime) = datetime.utcnow()  # type: ignore
    updated_at: Indexed(datetime) = datetime.utcnow()  # type: ignore

    @field_validator("academic_year")
    @classmethod
    def validate_academic_year(cls, v):
        if not re.match(r"^\d{4}", v):
            raise ValueError("Academic year must be in YYYY format")
        return v

    class Settings:
        name = "timetables"
        indexes = [
            [("academic_year", 1), ("department", 1), ("program", 1)],
        ]

        async def pre_save(self) -> None:
            self.updated_at = datetime.utcnow()
            if not self.created_at:
                self.created_at = self.updated_at

    class Config:
        arbitrary_types_allowed = True