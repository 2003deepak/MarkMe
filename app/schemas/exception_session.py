from pydantic import Field, model_validator
from typing import Optional, Literal, TYPE_CHECKING
from datetime import datetime
from pydantic import Field, model_validator
from beanie import Document, Indexed, Link

from app.schemas.session import Session
from app.schemas.subject import Subject
from app.schemas.teacher import Teacher

if TYPE_CHECKING:
    from app.schemas.swap_approval import SwapApproval


class ExceptionSession(Document):

    session: Optional[Link[Session]] = None
    subject: Optional[Link[Subject]] = None
    teacher: Optional[Link[Teacher]] = None

    date: Indexed(datetime)

    action: Literal["Cancel", "Reschedule", "Add"]
    reason: str

    start_time: Optional[str] = None
    end_time: Optional[str] = None

    # swap linkage
    swap_id: Optional[Link["SwapApproval"]] = None
    swap_role: Optional[Literal["SOURCE", "TARGET"]] = None

    created_by: Link[Teacher]

    created_at: Indexed(datetime) = Field(default_factory=datetime.utcnow)
    updated_at: Indexed(datetime) = Field(default_factory=datetime.utcnow)

    @model_validator(mode="after")
    def validate_exception_session(self):

        # session rules
        if self.action in {"Cancel", "Reschedule"} and self.session is None:
            raise ValueError("session is required")

        # time rules
        if self.action in {"Add", "Reschedule"}:
            if not self.start_time or not self.end_time:
                raise ValueError("start_time and end_time required")

        if self.action == "Cancel":
            if self.start_time or self.end_time:
                raise ValueError("time not allowed for Cancel")

        # swap rules
        if self.swap_id is not None:
            if self.action != "Reschedule":
                raise ValueError("swap allowed only for Reschedule")
            if self.swap_role not in {"SOURCE", "TARGET"}:
                raise ValueError("swap_role must be SOURCE or TARGET")

        return self

    class Settings:
        name = "exception_sessions"

        async def pre_save(self):
            self.updated_at = datetime.utcnow()

    class Config:
        arbitrary_types_allowed = True
