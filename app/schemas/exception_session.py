from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
from beanie import Document, Indexed, Link
from bson import ObjectId
from app.schemas.timetable import Timetable  
from app.schemas.subject import Subject  

class SlotReference(BaseModel):
    day: str
    slot_index: int = Field(..., alias="slotIndex")

    @field_validator("day")
    @classmethod
    def validate_day(cls, v):
        valid_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        if v not in valid_days:
            raise ValueError(f"Day must be one of: {valid_days}")
        return v

    @field_validator("slot_index")
    @classmethod
    def validate_slot_index(cls, v):
        if v < 0:
            raise ValueError("slotIndex must be at least 0")
        return v

class NewSession(BaseModel):
    start_time: str = Field(..., alias="startTime")
    end_time: str = Field(..., alias="endTime")
    subject: Optional[Link[Subject]] = None  # Changed to Link for subject reference

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time_format(cls, v):
        if not v or not isinstance(v, str) or v.count(":") != 1:
            raise ValueError("Time must be in HH:MM format")
        hours, minutes = map(int, v.split(":"))
        if not (0 <= hours <= 23 and 0 <= minutes <= 59):
            raise ValueError("Invalid time value")
        return v

class ExceptionSession(Document):
    timetable_id: Link[Timetable]  # Changed to Link for timetable reference
    date: Indexed(datetime)  # type: ignore
    action: str
    slot_reference: Optional[SlotReference] = Field(None, alias="slotReference")
    new_slot: Optional[NewSession] = Field(None, alias="newSlot")
    created_at: Indexed(datetime) = datetime.utcnow()  # type: ignore
    updated_at: Indexed(datetime) = datetime.utcnow()  # type: ignore

    @field_validator("action")
    @classmethod
    def validate_action(cls, v):
        if v not in ["Cancel", "Rescheduled", "Add"]:
            raise ValueError("Action must be either 'Cancel', 'Rescheduled' or 'Add'")
        return v

    @field_validator("slot_reference", mode="after")
    @classmethod
    def validate_slot_reference(cls, v, info):
        if info.data.get("action") == "Cancel" and not v:
            raise ValueError("slotReference is required when action is 'Cancel'")
        return v

    @field_validator("new_slot", mode="after")
    @classmethod
    def validate_new_slot(cls, v, info):
        if info.data.get("action") == "Add" and not v:
            raise ValueError("newSlot is required when action is 'Add'")
        return v

    

    class Settings:
        name = "exception_sessions"

        # Automatically update updated_at timestamp on save
        async def pre_save(self) -> None:
            self.updated_at = datetime.utcnow()
            if not self.created_at:
                self.created_at = self.updated_at