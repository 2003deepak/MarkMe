from beanie import Document, Indexed, Link, PydanticObjectId
from typing import List, Union, Optional
from datetime import datetime
from pydantic import Field
from app.schemas.student import Student
from app.schemas.teacher import Teacher
from app.schemas.clerk import Clerk

class FCMToken(Document):
    user_id: PydanticObjectId = Field(...)
    user_role: str = Field(...)   

    token: Indexed(str, unique=True)
    device_type: Optional[str] = None
    device_info: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_used_at: datetime = Field(default_factory=datetime.utcnow)
    active: bool = True

    class Settings:
        name = "fcm_tokens"
        indexes = [
            "user_id",
            "token",
            [("user_id", 1), ("token", 1)]
        ]