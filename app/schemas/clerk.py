from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
import re
from beanie import Document, Indexed
from datetime import datetime
import random

class Clerk(Document):
    first_name: str 
    middle_name: Optional[str]
    last_name: str 
    email: Indexed(EmailStr, unique=True) # type: ignore
    password: Optional[str] = None  # 6-digit numeric PIN
    department: str
    program: str
    phone: int = Field(..., alias="phone")
    profile_picture: Optional[str] = None
    profile_picture_id: Optional[str] = None 
    password_reset_otp: Optional[str] = None
    password_reset_otp_expires: Optional[datetime] = None
    created_at: Indexed(datetime) = datetime.utcnow() # type: ignore
    updated_at: Indexed(datetime) = datetime.utcnow() # type: ignore

    @field_validator("phone")
    def validate_phone(cls, v):
        v_str = str(v)
        if not re.match(r"^\d{10}$", v_str):
            raise ValueError("Phone number must be a 10-digit number")
        return v

    @field_validator("password")
    def validate_password(cls, v):
        if v is None:
            return v
        if v.startswith("$2b$"):  # Already hashed
            return v
        if not re.match(r"^\d{6}$", v):
            raise ValueError("Password must be a 6-digit numeric PIN")
        return v

    @field_validator("department")
    def validate_department(cls, v):
        if not v.strip():
            raise ValueError("Department cannot be empty")
        return v

    class Settings:
        name = "clerks"

        # Automatically update updated_at timestamp on save
        async def pre_save(self) -> None:
            self.updated_at = datetime.utcnow()
            if not self.created_at:
                self.created_at = self.updated_at