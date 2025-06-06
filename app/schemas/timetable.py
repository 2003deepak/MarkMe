from beanie import Document, Indexed
from pydantic import Field, field_validator
from typing import List, Dict, Optional

class Session(Document):
    start_time: str = Field(..., alias="startTime")  # Format example: "09:00"
    end_time: str = Field(..., alias="endTime")      # Format example: "10:00"
    subject: str = Field(..., alias="subject")       # ObjectId as string
    teacher: str = Field(..., alias="teacher")       # ObjectId as string

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time_format(cls, v):
        if not v or not isinstance(v, str) or v.count(":") != 1:
            raise ValueError("Time must be in HH:MM format")
        hours, minutes = map(int, v.split(":"))
        if not (0 <= hours <= 23 and 0 <= minutes <= 59):
            raise ValueError("Invalid time value")
        return v

    class Settings:
        name = "sessions"
        use_state_management = True


class Timetable(Document):
    academic_year: Indexed(str) = Field(..., alias="academicYear")
    department: Indexed(str)
    program: str
    term: str
    class_name: Indexed(str) = Field(..., alias="className")
    schedule: Dict[str, List[Session]] = {
        "Monday": [],
        "Tuesday": [],
        "Wednesday": [],
        "Thursday": [],
        "Friday": [],
        "Saturday": [],
        "Sunday": [],
    }

    @field_validator("academic_year")
    @classmethod
    def validate_academic_year(cls, v):
        import re
        if not re.match(r"^\d{4}-\d{2}$", v):
            raise ValueError("Academic year must be in YYYY-YY format")
        return v

    class Settings:
        name = "timetables"
        indexes = [
            [("academic_year", 1), ("department", 1), ("class_name", 1)]
        ]
        use_state_management = True
