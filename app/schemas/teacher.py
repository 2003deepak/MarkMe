from beanie import Document, Indexed, before_event, Insert, Update
from pydantic import EmailStr, HttpUrl, Field, field_validator
from typing import List, Optional
from passlib.context import CryptContext
from datetime import datetime
import re

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class Teacher(Document):
    teacher_id: Indexed(str) = Field(..., alias="teacherId")
    first_name: str = Field(..., alias="firstName")
    middle_name: Optional[str] = Field(None, alias="middleName")
    last_name: str = Field(..., alias="lastName")
    profile_picture: Optional[HttpUrl] = Field(None, alias="profilePicture")
    email: Indexed(EmailStr)
    password: str
    phone: str
    departments: List[str]
    title: str
    subjects_assigned: List[str] = Field(default_factory=list, alias="subjectsAssigned")  # ObjectId as string
    password_reset_token: Optional[str] = Field(None, alias="passwordResetToken")
    password_reset_expires: Optional[float] = Field(None, alias="passwordResetExpires")
    created_at: Optional[float] = Field(None, alias="createdAt")
    updated_at: Optional[float] = Field(None, alias="updatedAt")

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v):
        if not re.match(r"^\d{10}$", v):
            raise ValueError("Phone number must be 10 digits")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if not re.match(r"^\d{6}$", v):
            raise ValueError("Password must be a 6-digit number (MPIN)")
        return v

    @field_validator("departments")
    @classmethod
    def validate_departments(cls, v):
        if not v or len(v) == 0:
            raise ValueError("At least one department must be assigned")
        return v

    @field_validator("title")
    @classmethod
    def validate_title(cls, v):
        if v not in ["HOD", "Professor", "Assistant Professor"]:
            raise ValueError("Title must be one of: HOD, Professor, Assistant Professor")
        return v

    @before_event(Insert)
    async def set_timestamps_on_insert(self):
        now = datetime.utcnow().timestamp()
        self.created_at = now
        self.updated_at = now

    @before_event(Update)
    async def set_updated_at(self):
        self.updated_at = datetime.utcnow().timestamp()

    @before_event(Insert, Update)
    async def hash_password(self):
        if self.password and (self.is_modified("password") or self.is_new):
            self.password = pwd_context.hash(self.password)
            self.password_reset_token = None
            self.password_reset_expires = None

    class Settings:
        name = "teachers"
        indexes = [
            [("teacher_id", 1), ("email", 1), ("departments", 1)]
        ]
        use_state_management = True
