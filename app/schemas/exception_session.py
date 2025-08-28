from pydantic import BaseModel, Field, model_validator
from typing import Optional
from datetime import datetime
from beanie import Document, Indexed, Link
from app.schemas.session import Session


# Main ExceptionSession Document
class ExceptionSession(Document):
    session: Optional[Link[Session]] = None
    date: Indexed(datetime)
    action: str  # "Cancel", "Rescheduled", or "Add"
    start_time: Optional[str] = Field(None, alias="startTime")
    end_time: Optional[str] = Field(None, alias="endTime")
    created_at: Indexed(datetime) = Field(default_factory=datetime.utcnow)
    updated_at: Indexed(datetime) = Field(default_factory=datetime.utcnow)

    @model_validator(mode="after")
    def validate_fields_based_on_action(self):
        action = self.action
        valid_actions = ["Cancel", "Rescheduled", "Add"]
        
        # Validate action
        if action not in valid_actions:
            raise ValueError(f"Action must be one of: {valid_actions}")

        # Validate session for Cancel and Rescheduled
        if action in ["Cancel", "Rescheduled"] and self.session is None:
            raise ValueError("Field 'session' is required for Cancel and Rescheduled actions")

        # Validate start_time and end_time for Add and Rescheduled
        if action in ["Add", "Rescheduled"]:
            if not (self.start_time and self.end_time):
                raise ValueError("Fields 'startTime' and 'endTime' are required for Add and Rescheduled actions")

        # For Cancel action, start_time and end_time should be None
        if action == "Cancel" and (self.start_time is not None or self.end_time is not None):
            raise ValueError("Fields 'startTime' and 'endTime' should not be set for Cancel action")

        return self

    class Settings:
        name = "exception_sessions"

        async def pre_save(self) -> None:
            self.updated_at = datetime.utcnow()
            if not self.created_at:
                self.created_at = self.updated_at

    class Config:
        arbitrary_types_allowed = True