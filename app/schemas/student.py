from beanie import Document, Indexed, before_event, Insert, Update
from pydantic import EmailStr, HttpUrl, Field, field_validator
from typing import List, Optional
from passlib.context import CryptContext
from datetime import datetime, timedelta
import random
import re

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class Student(Document):
    student_id: Indexed(str) = Field(default=None, alias="studentId")
    first_name: str = Field(..., alias="firstName")
    middle_name: Optional[str] = Field(default=None, alias="middleName")
    last_name: str = Field(..., alias="lastName")
    email: Indexed(EmailStr)
    password: Optional[str] = None  # 6-digit numeric PIN
    profile_picture: Optional[HttpUrl] = Field(default=None, alias="profilePicture")
    dob: datetime
    roll_number: str = Field(..., alias="rollNumber")
    phone: str
    program: str
    department: str
    semester: int
    batch_year: int = Field(..., alias="batchYear")
    face_embedding: List[float] = Field(default_factory=list, alias="faceEmbedding")

    # OTP fields for password reset
    password_reset_otp: Optional[str] = Field(default=None, alias="passwordResetOtp")
    password_reset_otp_expires: Optional[datetime] = Field(default=None, alias="passwordResetOtpExpires")

    enrolled_date: datetime = Field(..., alias="enrolledDate")
    created_at: Optional[float] = Field(default=None, alias="createdAt")
    updated_at: Optional[float] = Field(default=None, alias="updatedAt")

    # Validators
    @field_validator("phone")
    def validate_phone(cls, v):
        if not re.match(r"^\d{10}$", v):
            raise ValueError("Phone number must be 10 digits")
        return v

    @field_validator("password", mode="before")
    def validate_password(cls, v):
        if v is None:
            return v
        if not re.match(r"^\d{6}$", v):
            raise ValueError("Password must be a 6-digit number (MPIN)")
        return v

    @field_validator("semester")
    def validate_semester(cls, v):
        if not (1 <= v <= 10):
            raise ValueError("Semester must be between 1 and 10")
        return v

    @field_validator("batch_year")
    def validate_batch_year(cls, v):
        if not (2000 <= v <= 2100):
            raise ValueError("Batch year must be between 2000 and 2100")
        return v

    @field_validator("face_embedding")
    def validate_face_embedding(cls, v):
        if len(v) != 0 and len(v) != 512:
            raise ValueError("faceEmbedding must be a 512-dimensional vector")
        return v

    # Lifecycle hooks
    @before_event(Insert)
    async def set_timestamps_and_student_id(self):
        now = datetime.utcnow().timestamp()
        self.created_at = now
        self.updated_at = now
        if not self.enrolled_date:
            self.enrolled_date = datetime.utcnow()
        # Generate student_id if missing
        if not self.student_id and self.department and self.batch_year and self.roll_number:
            self.student_id = f"{self.department}{self.batch_year}{self.roll_number}"

    @before_event(Update)
    async def set_updated_at(self):
        self.updated_at = datetime.utcnow().timestamp()

    @before_event(Insert, Update)
    async def hash_password(self):
        if self.password:
            self.password = pwd_context.hash(self.password)
            # Clear OTP on password change
            self.password_reset_otp = None
            self.password_reset_otp_expires = None

    # OTP management methods
    def generate_otp(self, expiry_minutes: int = 10) -> str:
        otp = f"{random.randint(100000, 999999)}"  # 6-digit numeric OTP
        self.password_reset_otp = otp
        self.password_reset_otp_expires = datetime.utcnow() + timedelta(minutes=expiry_minutes)
        return otp

    def verify_otp(self, otp: str) -> bool:
        if (
            self.password_reset_otp is None or
            self.password_reset_otp_expires is None or
            datetime.utcnow() > self.password_reset_otp_expires
        ):
            return False
        return otp == self.password_reset_otp

    class Settings:
        name = "students"
        indexes = [
            [("department", 1), ("semester", 1), ("batch_year", 1)]
        ]
        use_state_management = True
