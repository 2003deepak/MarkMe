from pydantic import EmailStr, Field, field_validator,BaseModel
from typing import Optional, List
from beanie import Document, Indexed
from datetime import datetime
import re


class AcademicScope(BaseModel):
    program_id: str
    department_id: str


class Clerk(Document):

    first_name: str
    middle_name: Optional[str] = None
    last_name: str

    email: Indexed(EmailStr, unique=True)  # type: ignore
    password: Optional[str] = None

    phone: Optional[int] = None

    academic_scopes: List[AcademicScope] = []

    profile_picture: Optional[str] = None
    profile_picture_id: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v):
        if v is not None:
            v_str = str(v)
            if not re.match(r"^\d{10}$", v_str):
                raise ValueError("Phone number must be a 10-digit number")
        return v


    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if v is None:
            return v
        if v.startswith("$2"):
            return v
        if not re.match(r"^\d{6}$", v):
            raise ValueError("Password must be a 6-digit numeric PIN")
        return v


    async def save(self, *args, **kwargs):
        self.updated_at = datetime.utcnow()
        return await super().save(*args, **kwargs)


    class Settings:
        name = "clerks"