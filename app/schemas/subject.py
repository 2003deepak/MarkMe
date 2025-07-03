from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient

class Subject(BaseModel):
    subject_code: str 
    subject_name: str
    department: str
    semester: int
    program: str
    type: str
    credit: int
    teacher_assigned: List[str] 

    @field_validator("subject_code")
    def uppercase_subject_code(cls, v):
        return v.upper()

    @field_validator("department")
    def uppercase_department(cls, v):
        return v.upper()

    @field_validator("semester")
    def validate_semester(cls, v):
        if not (1 <= v <= 10):
            raise ValueError("Semester must be between 1 and 10")
        return v

    @field_validator("type")
    def validate_type(cls, v):
        if v not in ["Lecture", "Lab"]:
            raise ValueError("Type must be either 'Lecture' or 'Lab'")
        return v

    @field_validator("credit")
    def validate_credit(cls, v):
        if not (1 <= v <= 10):
            raise ValueError("Credit must be between 1 and 10")
        return v

class SubjectRepository:
    def __init__(self, client: AsyncIOMotorClient, db_name: str):
        self.db = client[db_name]
        self.collection = self.db["subjects"]

    async def _ensure_indexes(self):
        await self.collection.create_index([("subject_code", 1), ("type", 1)], unique=True)
        await self.collection.create_index([("department", 1), ("semester", 1)])
        await self.collection.create_index("created_at")
        await self.collection.create_index("updated_at")

    async def _apply_timestamps(self, document: dict, is_update: bool = False) -> dict:
        now = datetime.utcnow()
        if not is_update and "created_at" not in document:
            document["created_at"] = now
        document["updated_at"] = now
        return document