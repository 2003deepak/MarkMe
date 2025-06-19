from pydantic import BaseModel, EmailStr, HttpUrl, Field, field_validator
from typing import List, Optional
from passlib.context import CryptContext
from datetime import datetime, timedelta
import re
import random
from motor.motor_asyncio import AsyncIOMotorClient

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class Teacher(BaseModel):
    teacher_id: str 
    first_name: str
    middle_name: Optional[str] = None
    last_name: str 
    profile_picture: Optional[HttpUrl] = None
    email: EmailStr
    password: Optional[str] = None 
    mobile_number: int
    department: str
    subjects_assigned: List[str] 
    password_reset_otp: Optional[str] = None
    password_reset_otp_expires: Optional[datetime] = None

    @field_validator("mobile_number")
    @classmethod
    def validate_phone(cls, v):
        if not re.match(r"^\d{10}$", str(v)):
            raise ValueError("Mobile Number must be 10 digits")
        return v

   

class TeacherRepository:
    def __init__(self, client: AsyncIOMotorClient, db_name: str):
        self.db = client[db_name]
        self.collection = self.db["teachers"]
        self._ensure_indexes()

    async def _ensure_indexes(self):
        await self.collection.create_index([("teacher_id", 1), ("email", 1), ("department", 1)], unique=True)

    async def _apply_timestamps(self, document: dict, is_update: bool = False) -> dict:
        now = datetime.utcnow()
        if not is_update and "created_at" not in document:
            document["created_at"] = now
        document["updated_at"] = now
        return document