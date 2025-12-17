from typing import Optional, Literal
from datetime import datetime
from pydantic import Field, model_validator
from beanie import Document, Indexed, Link

from app.schemas.session import Session
from app.schemas.subject import Subject
from app.schemas.teacher import Teacher


class ExceptionSession(Document):
    session: Optional[Link[Session]] = None
    subject: Optional[Link[Subject]] = None
    teacher: Optional[Link[Teacher]] = None

    date: Indexed(datetime)
    action: Literal["Cancel", "Rescheduled", "Add"]

    start_time: Optional[str] = None
    end_time: Optional[str] = None

    created_at: Indexed(datetime) = Field(default_factory=datetime.utcnow)
    updated_at: Indexed(datetime) = Field(default_factory=datetime.utcnow)

    @model_validator(mode="after")
    def validate_by_action(self):
        if self.action in ("Cancel", "Rescheduled") and self.session is None:
            raise ValueError("session is required for Cancel/Rescheduled")

        if self.action == "Add":
            if not self.subject or not self.teacher:
                raise ValueError("subject and teacher are required for Add")

        if self.action in ("Add", "Rescheduled"):
            if not self.start_time or not self.end_time:
                raise ValueError("start_time and end_time are required")

        if self.action == "Cancel" and (self.start_time or self.end_time):
            raise ValueError("Cancel should not have start_time or end_time")

        return self

    class Settings:
        name = "exception_sessions"

        async def pre_save(self):
            self.updated_at = datetime.utcnow()
