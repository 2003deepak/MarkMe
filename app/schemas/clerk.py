from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
from beanie import Document, Indexed
from datetime import datetime
import re

class Clerk(Document):
    first_name: str 
    middle_name: Optional[str] = None
    last_name: str 
    email: Indexed(EmailStr, unique=True)  # type: ignore
    password: Optional[str] = None  # 6-digit numeric PIN
    department: Optional[str] = None
    program: Optional[str] = None
    phone: Optional[int] = Field(None, alias="phone")
    profile_picture: Optional[str] = None
    profile_picture_id: Optional[str] = None 
    password_reset_otp: Optional[str] = None
    password_reset_otp_expires: Optional[datetime] = None
    created_at: Indexed(datetime) = datetime.utcnow()  # type: ignore
    updated_at: Indexed(datetime) = datetime.utcnow()  # type: ignore

    @field_validator("phone")
    def validate_phone(cls, v):
        if v is not None:
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
        if v is not None and not v.strip():
            raise ValueError("Department cannot be empty")
        return v

    @field_validator("program")
    def validate_program(cls, v):
        if v is not None and not v.strip():
            raise ValueError("Program cannot be empty")
        return v

    class Settings:
        name = "clerks"

        async def pre_save(self) -> None:
            self.updated_at = datetime.utcnow()
            if not self.created_at:
                self.created_at = self.updated_at