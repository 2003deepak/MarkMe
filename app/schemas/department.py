from beanie import Document, Link
from app.schemas.program import Program
from datetime import datetime

from app.schemas.program import Program
from pydantic import Field


class Department(Document):

    full_name: str
    department_code: str

    program_id: Link["Program"]

    is_active: bool = True

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


    class Settings:
        name = "departments"
        indexes = [
            [("department_code", 1)],
            [("program_id", 1)],
        ]