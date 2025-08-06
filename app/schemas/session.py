from beanie import Document, Link
from datetime import datetime
from pydantic import Field
from app.schemas.teacher import Teacher
from app.schemas.subject import Subject


class Session(Document):
    day: str
    start_time: str
    end_time: str
    subject: Link[Subject]
    teacher: Link[Teacher]

    academic_year: str
    department: str
    program: str
    semester: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "sessions"
        indexes = [
            ("day", "start_time"),
            ("subject",),
            ("teacher",),
            ("academic_year", "department", "program", "semester", "day")
        ]

    class Config:
        json_encoders = {datetime: lambda dt: dt.isoformat()}