from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.routes import auth_router, student_router, admin_router, clerk_router, system_router, teacher_router , time_table_router , attendance_router
from app.core.database import init_db, close_db
from app.core.config import settings
from app.core.rabbit_setup import setup_rabbitmq
from app.middleware.auth_middleware import AuthMiddleware  # Make sure you import your middleware

# Routes that do NOT require authentication
WHITELIST = [
    "/"
    "/docs",
    "/openapi.json",  
    "/api/v1/auth/login",
    "/api/v1/auth/refresh-token",
    "/api/v1/auth/forgot-password"
    "/api/v1/auth/verify-otp",
    "/api/v1/reset-password",
    "/api/v1/student/",
    "/api/v1/student/verify-email"
]

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("📦 Connecting to DB...")
    await init_db()

    print("🔄 Initializing RabbitMQ...")
    await setup_rabbitmq()

    yield  # Application runs here

    print("🧹 Closing DB connection...")
    await close_db()

# Initialize FastAPI app with lifespan
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="A FastAPI project",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500"],  # Your frontend origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add Auth middleware (token validation)
app.add_middleware(AuthMiddleware, whitelist=WHITELIST)

# Include routers
app.include_router(auth_router.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(system_router.router, prefix="/api/v1/system", tags=["System Check"])
app.include_router(student_router.router, prefix="/api/v1/student", tags=["Students"])
app.include_router(admin_router.router, prefix="/api/v1/admin", tags=["Admin"])
app.include_router(clerk_router.router, prefix="/api/v1/clerk", tags=["Clerk"])
app.include_router(teacher_router.router, prefix="/api/v1/teacher", tags=["Teacher"])
app.include_router(time_table_router.router, prefix="/api/v1/timetable", tags=["Timetable"])
app.include_router(attendance_router.router, prefix="/api/v1/attendance", tags=["Attendance"])

# Root endpoint
@app.get("/")
async def root():
    return {"message": "Welcome to the MarkMe API"}
