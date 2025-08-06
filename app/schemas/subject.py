from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import datetime
from beanie import Document, Link
from app.schemas.teacher import Teacher

class Component(BaseModel):
    type: str  # Lecture or Lab

    @field_validator("type")
    @classmethod
    def validate_type(cls, v):
        if v not in ["Lecture", "Lab"]:
            raise ValueError("Type must be either 'Lecture' or 'Lab'")
        return v

class Subject(Document):
    subject_code: str
    subject_name: str
    department: str
    semester: int
    program: str
    component: str
    credit: int
    teacher_assigned: Link["Teacher"] = None  # Assuming Teacher is defined elsewhere

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

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

    @field_validator("credit")
    @classmethod
    def validate_credit(cls, v):
        if not (1 <= v <= 10):
            raise ValueError("Credit must be between 1 and 10")
        return v
    
    @field_validator("component")
    @classmethod
    def validate_component(cls, v):
        if v not in ["Lecture", "Lab"]:
            raise ValueError("Component must be either 'Lecture' or 'Lab'")
        return v

    class Settings:
        name = "subjects"
        indexes = [
            [("subject_code", 1), ("component", 1)],
            [("department", 1), ("semester", 1)],
            "created_at",
            "updated_at",
        ]

    async def pre_save(self) -> None:
        self.updated_at = datetime.utcnow()
        if not self.created_at:
            self.created_at = self.updated_at

    class Config:
        arbitrary_types_allowed = True

