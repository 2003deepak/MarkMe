from pydantic import Field, field_validator
from typing import Optional
from datetime import datetime
from beanie import Document, Indexed, Link
from app.schemas.session import Session
from app.schemas.exception_session import ExceptionSession
from app.schemas.subject import Subject  

class Attendance(Document):
    session: Optional[Link[Session]] = None
    exception_session: Optional[Link[ExceptionSession]] = None
    date: Indexed(datetime)
    students: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

   

    class Settings:
        name = "attendances"
        indexes = [
            ("session", "date"),
            ("session"),
            ("date",),
        ]

        async def pre_save(self) -> None:
            self.updated_at = datetime.utcnow()
            if not self.created_at:
                self.created_at = self.updated_at

    class Config:
        arbitrary_types_allowed = True
