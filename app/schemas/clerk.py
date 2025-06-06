from beanie import Document, Indexed, before_event, Insert, Update
from pydantic import EmailStr, HttpUrl, Field, field_validator
from typing import Optional
from passlib.context import CryptContext
from datetime import datetime

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class Clerk(Document):
    first_name: str = Field(..., alias="firstName")
    middle_name: Optional[str] = Field(None, alias="middleName")
    last_name: str = Field(..., alias="lastName")
    email: Indexed(EmailStr)
    password: str
    department: str
    phone: str
    profile_picture: Optional[HttpUrl] = Field(None, alias="profilePicture")
    password_reset_token: Optional[str] = Field(None, alias="passwordResetToken")
    password_reset_expires: Optional[float] = Field(None, alias="passwordResetExpires")
    created_at: Optional[float] = Field(None, alias="createdAt")
    updated_at: Optional[float] = Field(None, alias="updatedAt")

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v):
        import re
        if not re.match(r"^\d{10}$", v):
            raise ValueError("Phone number must be 10 digits")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        import re
        if not re.match(r"^\d{6}$", v):
            raise ValueError("Password must be a 6-digit numeric PIN")
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

    class Settings:
        name = "clerks"
        use_state_management = True
