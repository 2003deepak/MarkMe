from beanie import Document
from datetime import datetime
from pydantic import Field

class OTP(Document):
    email_or_phone: str
    otp: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime

    class Settings:
        name = "otp"
