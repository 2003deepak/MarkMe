from beanie import Document, Indexed, before_event, Insert, Update
from pydantic import Field, field_validator
from typing import Optional
from datetime import datetime

class SlotReference(Document):
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

    class Settings:
        name = "slot_references"
        use_state_management = True

class NewSlot(Document):
    start_time: str = Field(..., alias="startTime")
    end_time: str = Field(..., alias="endTime")
   

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time_format(cls, v):
        if not v or not isinstance(v, str) or v.count(":") != 1:
            raise ValueError("Time must be in HH:MM format")
        hours, minutes = map(int, v.split(":"))
        if not (0 <= hours <= 23 and 0 <= minutes <= 59):
            raise ValueError("Invalid time value")
        return v

    class Settings:
        name = "new_slots"
        use_state_management = True

class ExceptionTimetable(Document):
    timetable_id: Indexed(str) = Field(..., alias="timetableId")  # ObjectId as string
    date: Indexed(datetime)
    action: str
    slot_reference: Optional[SlotReference] = Field(None, alias="slotReference")
    new_slot: Optional[NewSlot] = Field(None, alias="newSlot")
   
    @field_validator("action")
    @classmethod
    def validate_action(cls, v):
        if v not in ["Cancel", "Rescheduled" , "Add"]:
            raise ValueError("Action must be either 'Cancel' or 'Add'")
        return v

    # Cross-field validation with mode="after" so all fields are available
    @field_validator("slot_reference", mode="after")
    @classmethod
    def validate_slot_reference(cls, v, info):
        action = info.data.get("action")
        if action == "Cancel" and not v:
            raise ValueError("slotReference with day and slotIndex is required when action is 'Cancel'")
        return v

    @field_validator("new_slot", mode="after")
    @classmethod
    def validate_new_slot(cls, v, info):
        action = info.data.get("action")
        if action == "Add" and not v:
            raise ValueError("newSlot with startTime, endTime, subject, teacher, and room is required when action is 'Add'")
        return v

    @before_event(Insert)
    async def set_timestamps_on_insert(self):
        now = datetime.utcnow().timestamp()
        self.created_at = now
        self.updated_at = now

    @before_event(Update)
    async def set_updated_at(self):
        self.updated_at = datetime.utcnow().timestamp()

    class Settings:
        name = "exception_timetables"
        indexes = [
            [("timetable_id", 1), ("date", 1)]
        ]
        use_state_management = True
