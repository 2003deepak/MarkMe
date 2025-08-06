from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
from beanie import Document, Indexed, Link
from app.schemas.session import Session
from app.schemas.subject import Subject
from app.schemas.teacher import Teacher

# NewSession represents a new or modified session
class NewSession(BaseModel):
    start_time: str = Field(..., alias="startTime")
    end_time: str = Field(..., alias="endTime")
    subject: Link[Subject] 
    teacher : Link[Teacher]

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time_format(cls, v):
        if not v or not isinstance(v, str) or v.count(":") != 1:
            raise ValueError("Time must be in HH:MM format")
        hours, minutes = map(int, v.split(":"))
        if not (0 <= hours <= 23 and 0 <= minutes <= 59):
            raise ValueError("Invalid time value")
        return v

# Main ExceptionSession Document
class ExceptionSession(Document):
    session: [Session]
    date: Indexed(datetime)
    action: str  # "Cancel", "Rescheduled", or "Add"
    new_slot: Optional[NewSession] = Field(None, alias="newSlot")  # For "Add" or "Rescheduled"
    created_at: Indexed(datetime) = Field(default_factory=datetime.utcnow)
    updated_at: Indexed(datetime) = Field(default_factory=datetime.utcnow)

    @field_validator("action")
    @classmethod
    def validate_action(cls, v):
        valid_actions = ["Cancel", "Rescheduled", "Add"]
        if v not in valid_actions:
            raise ValueError(f"Action must be one of: {valid_actions}")
        return v

    @field_validator("session", mode="after")
    @classmethod
    def validate_session_required(cls, v, info):
        if info.data.get("action") in ["Cancel", "Rescheduled"] and not v:
            raise ValueError("Field 'session' is required for Cancel and Rescheduled actions")
        return v

    @field_validator("new_slot", mode="after")
    @classmethod
    def validate_new_slot_required(cls, v, info):
        if info.data.get("action") in ["Add", "Rescheduled"] and not v:
            raise ValueError("Field 'newSlot' is required for Add and Rescheduled actions")
        return v

    class Settings:
        name = "exception_sessions"

        async def pre_save(self) -> None:
            self.updated_at = datetime.utcnow()
            if not self.created_at:
                self.created_at = self.updated_at

    class Config:
        arbitrary_types_allowed = True
