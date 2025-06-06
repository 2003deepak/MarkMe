from beanie import Document, Indexed, before_event, Insert, Update
from pydantic import EmailStr, HttpUrl, Field, field_validator
from typing import List, Optional
from passlib.context import CryptContext
from datetime import datetime

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class Student(Document):
    student_id: Indexed(str) = Field(default=None, alias="studentId")
    first_name: str = Field(..., alias="firstName")
    middle_name: Optional[str] = Field(default=None, alias="middleName")
    last_name: str = Field(..., alias="lastName")
    email: Indexed(EmailStr)
    password: Optional[str] = None
    profile_picture: Optional[HttpUrl] = Field(default=None, alias="profilePicture")
    dob: datetime
    roll_number: str = Field(..., alias="rollNumber")
    phone: str
    program: str
    department: str
    semester: int
    batch_year: int = Field(..., alias="batchYear")
    face_embedding: List[float] = Field(default_factory=list, alias="faceEmbedding")
    password_reset_token: Optional[str] = Field(default=None, alias="passwordResetToken")
    password_reset_expires: Optional[float] = Field(default=None, alias="passwordResetExpires")
    enrolled_date: datetime = Field(..., alias="enrolledDate")
    created_at: Optional[float] = Field(default=None, alias="createdAt")
    updated_at: Optional[float] = Field(default=None, alias="updatedAt")

    # Pydantic v2 style validators
    @field_validator("phone")
    def validate_phone(cls, v):
        import re
        if not re.match(r"^\d{10}$", v):
            raise ValueError("Phone number must be 10 digits")
        return v

    @field_validator("password", mode="before")
    def validate_password(cls, v):
        import re
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

    @before_event(Insert)
    async def set_timestamps_and_student_id(self):
        now = datetime.utcnow().timestamp()
        self.created_at = now
        self.updated_at = now
        if not self.enrolled_date:
            self.enrolled_date = datetime.utcnow()
        # Generate student_id
        if not self.student_id and self.department and self.batch_year and self.roll_number:
            self.student_id = f"{self.department}{self.batch_year}{self.roll_number}"

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
        name = "students"
        indexes = [
            [("department", 1), ("semester", 1), ("batch_year", 1)]
        ]
        use_state_management = True