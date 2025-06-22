from datetime import datetime
from typing import List, Optional
import re
from pydantic import BaseModel, EmailStr, Field, field_validator, HttpUrl
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

class Student(BaseModel):
    student_id: str 
    first_name: str 
    middle_name: Optional[str] 
    last_name: str 
    email: str
    password: str
    profile_picture: Optional[HttpUrl] = None
    dob: str
    roll_number: int 
    phone: int
    program: str
    department: str
    semester: int
    batch_year: int 
    face_embedding: Optional[List[float]] = None
    password_reset_otp: Optional[str] = None
    password_reset_otp_expires: Optional[datetime] = None

    # Validators
    @field_validator("phone")
    def validate_phone(cls, v):
        # Convert int to string for length and digit validation
        v_str = str(v)
        if not re.match(r"^\d{10}$", v_str):
            raise ValueError("Phone number must be a 10-digit number")
        return v

    @field_validator("roll_number")
    def validate_roll_number(cls, v):
        # Ensure roll_number is a positive integer
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
        if v is None or v == []:  # Accept both None and empty list
            return None
        if not isinstance(v, list) or len(v) != 512:
            raise ValueError("faceEmbedding must be a 512-dimensional vector")
        return v


    @field_validator("dob")
    def validate_dob(cls, v):
        # Validate that dob is in YYYY-MM-DD format
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            raise ValueError("DOB must be in YYYY-MM-DD format")
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Invalid date format or invalid date")
        return v

class StudentRepository:
    def __init__(self, client: AsyncIOMotorClient, db_name: str):
        self.db = client[db_name]
        self.collection = self.db["students"]
        self._ensure_indexes()

    async def _ensure_indexes(self):
        await self.collection.create_index("student_id", unique=True)
        await self.collection.create_index("email", unique=True)
        await self.collection.create_index("roll_number", unique=True)  
        await self.collection.create_index([("department", 1), ("semester", 1), ("batch_year", 1)])
        await self.collection.create_index("created_at")
        await self.collection.create_index("updated_at")

    async def _apply_timestamps(self, document: dict, is_update: bool = False) -> dict:
        now = datetime.utcnow()
        if not is_update and "created_at" not in document:
            document["created_at"] = now
        document["updated_at"] = now
        return document