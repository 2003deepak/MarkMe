from datetime import datetime, date
from typing import Annotated, List, Optional
import re
from pydantic import BaseModel, EmailStr, HttpUrl, Field, field_validator
from beanie import Document, Indexed


class Student(Document):
    # --- Personal Info ---
    first_name: str
    middle_name: Optional[str] = None
    last_name: str
    email: Annotated[EmailStr, Indexed(unique=True)]
    password: str
    profile_picture: Optional[HttpUrl] = None
    profile_picture_id: Optional[str] = None
    dob: Optional[date] = None

    roll_number: Optional[int] = Indexed(unique=True, sparse=True)
    phone: Optional[int] = None
    program: Optional[str] = None
    department: Optional[str] = Indexed()
    semester: Optional[int] = Indexed()
    batch_year: Optional[int] = Indexed()

    face_embedding: Optional[List[float]] = None

    password_reset_otp: Optional[str] = None
    password_reset_otp_expires: Optional[datetime] = None
    is_verified: bool = False

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # --- Validators ---
    @field_validator("phone")
    def validate_phone(cls, v):
        if v is None:
            return None
        v_str = str(v)
        if not re.match(r"^\d{10}$", v_str):
            raise ValueError("Phone number must be a valid 10-digit number")
        return int(v_str)

    @field_validator("roll_number")
    def validate_roll_number(cls, v):
        if v is None:
            return None
        if v <= 0:
            raise ValueError("Roll number must be a positive integer")
        return v

    @field_validator("semester")
    def validate_semester(cls, v):
        if v is None:
            return None
        if not (1 <= v <= 10):
            raise ValueError("Semester must be between 1 and 10")
        return v

    @field_validator("batch_year")
    def validate_batch_year(cls, v):
        if v is None:
            return None
        if not (2000 <= v <= 2100):
            raise ValueError("Batch year must be between 2000 and 2100")
        return v

    @field_validator("face_embedding")
    def validate_face_embedding(cls, v):
        if v is None:
            return None
        if not isinstance(v, list) or len(v) != 512:
            raise ValueError("faceEmbedding must be a 512-dimensional vector")
        return v

    class Settings:
        name = "students"
        indexes = [
            [("department", 1), ("semester", 1), ("batch_year", 1)], 
            "email",
            "roll_number",
            "department",
            "semester",
            "batch_year",
        ]

    # --- Hooks ---
    async def pre_save(self) -> None:
        """Auto-update timestamps before saving."""
        self.updated_at = datetime.utcnow()
        if not self.created_at:
            self.created_at = self.updated_at
