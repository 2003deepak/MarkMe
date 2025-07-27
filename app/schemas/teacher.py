from pydantic import BaseModel, EmailStr, HttpUrl, Field, field_validator
from typing import List, Optional
from passlib.context import CryptContext
from datetime import datetime
from beanie import Document, Indexed, Link
import re

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class Teacher(Document):
    teacher_id: Indexed(str, unique=True)  # type: ignore
    first_name: str
    middle_name: Optional[str] = None
    last_name: str 
    profile_picture: Optional[HttpUrl] = None
    profile_picture_id: Optional[str] = None 
    email: Indexed(EmailStr, unique=True)  # type: ignore
    password: Optional[str] = None 
    mobile_number: int
    department: Indexed(str)  # type: ignore
    subjects_assigned: List[Link["Subject"]] = []  # Use string-based forward reference
    password_reset_otp: Optional[str] = None
    password_reset_otp_expires: Optional[datetime] = None
    created_at: Indexed(datetime) = datetime.utcnow()  # type: ignore
    updated_at: Indexed(datetime) = datetime.utcnow()  # type: ignore

    @field_validator("mobile_number")
    @classmethod
    def validate_phone(cls, v):
        if not re.match(r"^\d{10}$", str(v)):
            raise ValueError("Mobile Number must be 10 digits")
        return v
    
    class Settings:
        name = "teachers"
        indexes = [
            [("teacher_id", 1), ("email", 1), ("department", 1)],
        ]

        # Automatically update updated_at timestamp on save
        async def pre_save(self) -> None:
            self.updated_at = datetime.utcnow()
            if not self.created_at:
                self.created_at = self.updated_at

    class Config:
        arbitrary_types_allowed = True