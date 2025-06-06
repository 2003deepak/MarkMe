from fastapi import FastAPI
from contextlib import asynccontextmanager

from app.api.v1.api_v1_router import api_v1_router
from app.core.database import init_db , close_db

from fastapi.middleware.cors import CORSMiddleware



@asynccontextmanager
async def lifespan(app: FastAPI):
    print("📦 Connecting to DB...")
    await init_db()
    yield
    print("🧹 Closing DB connection...")
    await close_db()

app = FastAPI(
    title="MarkMe API",
    description="A FastAPI project",
    version="1.0.0",
    lifespan=lifespan  
)


# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global API v1 routes
app.include_router(api_v1_router, prefix="/api")

@app.get("/")
async def root():
    return {"message": "Welcome to the MarkMe API"}
