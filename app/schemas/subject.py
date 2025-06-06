from beanie import Document, Indexed, before_event, Insert, Update
from pydantic import Field, field_validator
from typing import List, Optional
from datetime import datetime

class Subject(Document):
    subject_code: Indexed(str) = Field(..., alias="subjectCode")
    name: str
    department: str
    semester: int
    type: str
    credit_hours: int = Field(..., alias="creditHours")
    teacher_assigned: List[str] = Field(..., alias="teacherAssigned")  # ObjectId as string
    created_at: Optional[float] = Field(None, alias="createdAt")
    updated_at: Optional[float] = Field(None, alias="updatedAt")

    @field_validator("subject_code")
    @classmethod
    def uppercase_subject_code(cls, v):
        return v.upper()

    @field_validator("department")
    @classmethod
    def uppercase_department(cls, v):
        return v.upper()

    @field_validator("semester")
    @classmethod
    def validate_semester(cls, v):
        if not (1 <= v <= 10):
            raise ValueError("Semester must be between 1 and 10")
        return v

    @field_validator("type")
    @classmethod
    def validate_type(cls, v):
        if v not in ["Lecture", "Lab"]:
            raise ValueError("Type must be either 'Lecture' or 'Lab'")
        return v

    @field_validator("credit_hours")
    @classmethod
    def validate_credit_hours(cls, v):
        if not (1 <= v <= 10):
            raise ValueError("Credit hours must be between 1 and 10")
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
        name = "subjects"
        indexes = [
            [("department", 1), ("semester", 1)]
        ]
        use_state_management = True
