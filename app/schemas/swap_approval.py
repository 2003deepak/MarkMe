from pydantic import Field, model_validator
from typing import Literal, Optional, TYPE_CHECKING
from datetime import datetime
from beanie import Document, Indexed, Link

from app.schemas.session import Session
from app.schemas.teacher import Teacher

if TYPE_CHECKING:
    from app.schemas.exception_session import ExceptionSession


class SwapApproval(Document):

    exception: Link["ExceptionSession"]

    source_session: Link[Session]
    target_session: Link[Session]

    requested_by: Link[Teacher]
    requested_to: Link[Teacher]

    status: Literal["PENDING", "APPROVED", "REJECTED"] = "PENDING"

    created_at: Indexed(datetime) = Field(default_factory=datetime.utcnow)
    responded_at: Optional[datetime] = None

    @model_validator(mode="after")
    def validate_swap(self):
        if self.requested_by == self.requested_to:
            raise ValueError("requested_by and requested_to cannot be the same")

        if self.source_session == self.target_session:
            raise ValueError("source_session and target_session must be different")

        return self

    class Settings:
        name = "swap_approvals"

        async def pre_save(self):
            if self.status in {"APPROVED", "REJECTED"} and self.responded_at is None:
                self.responded_at = datetime.utcnow()

    class Config:
        arbitrary_types_allowed = True
