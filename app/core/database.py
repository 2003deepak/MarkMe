from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from typing import Optional
from app.core.config import settings
from app.schemas.timetable import Timetable, Session
from app.schemas.teacher import Teacher
from app.schemas.clerk import Clerk
from app.schemas.exception_timetable import ExceptionTimetable, SlotReference, NewSlot
from app.schemas.student import Student
from app.schemas.subject import Subject
from app.schemas.attendance import Attendance

# Global client to hold the MongoDB connection
client: Optional[AsyncIOMotorClient] = None

async def init_db():
    global client
    # Create MongoDB client using settings.MONGO_URI
    client = AsyncIOMotorClient(settings.MONGO_URI)

    # Use MONGO_DB_NAME if set, otherwise extract from MONGO_URI
    if settings.MONGO_DB_NAME:
        db_name = settings.MONGO_DB_NAME
    else:
        # Extract database name from the URI
        db_name = settings.MONGO_URI.split("/")[-1].split("?")[0]

    # Initialize Beanie with the database and models
    await init_beanie(
        database=client[db_name],
        document_models=[
            Timetable,
            Session,
            Teacher,
            Clerk,
            ExceptionTimetable,
            SlotReference,
            NewSlot,
            Student,
            Subject,
            Attendance
        ]
    )

    print(f"Database '{db_name}' connected successfully!")

async def close_db():
    if client:
        client.close()