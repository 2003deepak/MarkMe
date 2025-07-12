from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
import re
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
import random

class Clerk(BaseModel):

    first_name: str 
    middle_name: Optional[str]
    last_name: str 
    email: EmailStr
    password: Optional[str] = None  # 6-digit numeric PIN
    department: str
    program:str
    phone: int = Field(..., alias="phone")
    profile_picture: Optional[str] = None
    profile_picture_id : str = None 
    password_reset_otp: Optional[str] = None
    password_reset_otp_expires: Optional[datetime] = None
    

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

class ClerkRepository:
    def __init__(self, client: AsyncIOMotorClient, db_name: str):
        self.db = client[db_name]
        self.collection = self.db["clerks"]
        self._ensure_indexes()

    async def _ensure_indexes(self):

        await self.collection.create_index("email", unique=True)
        await self.collection.create_index("created_at")
        await self.collection.create_index("updated_at")

    async def _apply_timestamps(self, document: dict, is_update: bool = False) -> dict:
        now = datetime.utcnow()
        if not is_update and "created_at" not in document:
            document["created_at"] = now
        document["updated_at"] = now
        return document
