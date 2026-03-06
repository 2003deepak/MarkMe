from beanie import Document
from datetime import datetime
from pydantic import Field, field_validator 


class Program(Document):

    program_code: str
    full_name: str
    duration_years: int

    is_active: bool = True

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


    @field_validator("duration_years")
    @classmethod
    def validate_duration_years(cls, v: int) -> int:
        if v < 1 or v > 5:
            raise ValueError("Duration years must be between 1 and 5")
        return v

    


    class Settings:
        name = "programs"
        indexes = [
            [("program_code", 1)]
        ]