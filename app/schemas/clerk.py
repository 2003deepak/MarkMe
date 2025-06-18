from beanie import Document, Indexed, before_event, Insert, Update
from pydantic import EmailStr, HttpUrl, Field, field_validator
from typing import Optional
from passlib.context import CryptContext
from datetime import datetime, timedelta
import random
import re

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class Clerk(Document):
    first_name: str = Field(..., alias="firstName")
    middle_name: Optional[str] = Field(None, alias="middleName")
    last_name: str = Field(..., alias="lastName")
    email: Indexed(EmailStr)
    password: Optional[str] = None # 6-digit numeric PIN
    department: str
    phone: str
    profile_picture: Optional[HttpUrl] = Field(None, alias="profilePicture")

    # OTP fields for password reset
    password_reset_otp: Optional[str] = Field(None, alias="passwordResetOtp")
    password_reset_otp_expires: Optional[datetime] = Field(None, alias="passwordResetOtpExpires")

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
        if v is None:
            return v  
        if v.startswith("$2b$"):
            return v
        if not re.match(r"\d{6}", v):
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
        if self.password :
            self.password = pwd_context.hash(self.password)
            # Clear OTP fields on password change
            self.password_reset_otp = None
            self.password_reset_otp_expires = None

    # OTP management methods
    def generate_otp(self, expiry_minutes: int = 10) -> str:
        otp = f"{random.randint(100000, 999999)}"  # 6-digit OTP
        self.password_reset_otp = otp
        self.password_reset_otp_expires = datetime.utcnow() + timedelta(minutes=expiry_minutes)
        return otp

    def verify_otp(self, otp: str) -> bool:
        if (
            self.password_reset_otp is None
            or self.password_reset_otp_expires is None
            or datetime.utcnow() > self.password_reset_otp_expires
        ):
            return False
        return otp == self.password_reset_otp

    class Settings:
        name = "clerks"
        use_state_management = True
