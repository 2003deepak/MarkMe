from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional
from app.core.config import settings
import pymongo

# Global client to hold the MongoDB connection
client: Optional[AsyncIOMotorClient] = None
db = None

async def init_db():
    global client, db
    
    # Create MongoDB client
    client = AsyncIOMotorClient(settings.MONGO_URI)
    
    # Get database name
    if settings.MONGO_DB_NAME:
        db_name = settings.MONGO_DB_NAME
    else:
        # Extract database name from URI
        db_name = settings.MONGO_URI.split("/")[-1].split("?")[0]
    
    db = client[db_name]
    
    print(f"Database '{db_name}' connected successfully!")

async def close_db():
    if client:
        client.close()

def get_db():
    """Get the database instance"""
    if db is None:  # Explicitly check if db is None
        raise RuntimeError("Database not initialized")
    return db