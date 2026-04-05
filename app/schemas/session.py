from beanie import Document, Link
from datetime import datetime
from pydantic import Field

from app.schemas.clerk import Clerk


class Session(Document):
    day: str
    start_time: str
    end_time: str

    subject: Link["Subject"]
    teacher: Link["Teacher"]

    academic_year: str
    department: str
    program: str
    semester: str

    is_active: bool = True
    deleted_by: Link["Clerk"] | None = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime | None = None

    class Settings:
        name = "sessions"
        indexes = [
            ("is_active", "day"),
            ("teacher", "day"),
            ("subject",),
            ("academic_year", "department", "program", "semester", "day", "is_active"),
        ]

    class Config:
        json_encoders = {datetime: lambda dt: dt.isoformat()}