from datetime import datetime
from typing import List, Optional
import re
from pydantic import BaseModel, EmailStr, Field, field_validator, HttpUrl
from beanie import Document, Indexed, Link
from bson import ObjectId
from datetime import date

class Student(Document):
    student_id: Indexed(str, unique=True)  # type: ignore
    first_name: str 
    middle_name: Optional[str] 
    last_name: str 
    email: Indexed(EmailStr, unique=True)  # type: ignore
    password: str
    profile_picture: Optional[HttpUrl] = None
    profile_picture_id: Optional[str] = None 
    dob: date
    roll_number: Indexed(int, unique=True)  # type: ignore
    phone: str
    program: str
    department: Indexed(str)  # type: ignore
    semester: Indexed(int)  # type: ignore
    batch_year: Indexed(int)  # type: ignore
    face_embedding: Optional[List[float]] = None
    password_reset_otp: Optional[str] = None
    password_reset_otp_expires: Optional[datetime] = None
    created_at: Indexed(datetime) = datetime.utcnow()  # type: ignore
    updated_at: Indexed(datetime) = datetime.utcnow()  # type: ignore

    # Validators (unchanged)
    @field_validator("phone")
    def validate_phone(cls, v):
        v_str = str(v)
        if not re.match(r"^\d{10}$", v_str):
            raise ValueError("Phone number must be a 10-digit number")
        return v

    @field_validator("roll_number")
    def validate_roll_number(cls, v):
        if v <= 0:
            raise ValueError("Roll number must be a positive integer")
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
        if v is None or v == []:
            return None
        if not isinstance(v, list) or len(v) != 512:
            raise ValueError("faceEmbedding must be a 512-dimensional vector")
        return v



    class Settings:
        name = "students"
        indexes = [
            [("department", 1), ("semester", 1), ("batch_year", 1)],
        ]

        async def pre_save(self) -> None:
            self.updated_at = datetime.utcnow()
            if not self.created_at:
                self.created_at = self.updated_at