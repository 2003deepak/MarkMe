from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.routes import auth_router, student_router, admin_router, clerk_router, system_router
from app.core.database import init_db, close_db
from app.core.config import settings
from app.core.rabbit_setup import setup_rabbitmq

# Initialize FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="A FastAPI project",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(system_router.router, prefix="/api/v1/system", tags=["System Check"])
app.include_router(student_router.router, prefix="/api/v1/student", tags=["Students"])
app.include_router(admin_router.router, prefix="/api/v1/admin", tags=["Admin"])
app.include_router(clerk_router.router, prefix="/api/v1/clerk", tags=["Clerk"])

# Startup event to initialize database
@app.on_event("startup")
async def startup_event():
    print("📦 Connecting to DB...")
    print("🔄 Initializing Rabbit MQ...")
    await init_db()
    await setup_rabbitmq()

# Shutdown event to close database connection
@app.on_event("shutdown")
async def shutdown_event():
    print("🧹 Closing DB connection...")
    await close_db()

# Root endpoint
@app.get("/")
async def root():
    return {"message": "Welcome to the MarkMe API"}