from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDocument, AsyncIOMotorCollection
from bson import ObjectId


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
    subject: Optional[str]

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time_format(cls, v):
        if not v or not isinstance(v, str) or v.count(":") != 1:
            raise ValueError("Time must be in HH:MM format")
        hours, minutes = map(int, v.split(":"))
        if not (0 <= hours <= 23 and 0 <= minutes <= 59):
            raise ValueError("Invalid time value")
        return v

class ExceptionSession(BaseModel):
    timetable_id: str
    date: datetime
    action: str
    slot_reference: Optional[SlotReference] = Field(None, alias="slotReference")
    new_slot: Optional[NewSession] = Field(None, alias="newSlot")
    created_at: Optional[float] = None
    updated_at: Optional[float] = None

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


class SlotReferenceDocument:
    def __init__(self, day: str, slot_index: int):
        self.day = day
        self.slot_index = slot_index



class NewSessionDocument:
    def __init__(self, start_time: str, end_time: str, subject: Optional[str] = None):
        self.start_time = start_time
        self.end_time = end_time
        self.subject = subject


class ExceptionSessionDocument(AsyncIOMotorDocument):
    class Settings:
        collection = "exception_sessions"

    def __init__(
        self,
        timetable_id: str,
        date: datetime,
        action: str,
        slot_reference: Optional[SlotReferenceDocument] = None,
        new_slot: Optional[NewSessionDocument] = None,
        created_at: Optional[float] = None,
        updated_at: Optional[float] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.timetable_id = timetable_id
        self.date = date
        self.action = action
        self.slot_reference = slot_reference
        self.new_slot = new_slot
        self.created_at = created_at
        self.updated_at = updated_at

    