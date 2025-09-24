from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional
from app.core.config import settings
from app.schemas.student import Student   
from app.schemas.teacher import Teacher
from app.schemas.clerk import Clerk
from app.schemas.subject import Subject
from app.schemas.attendance import Attendance
from app.schemas.exception_session import ExceptionSession
from app.schemas.student_attendance_summary import StudentAttendanceSummary
from app.schemas.attendance_heatmap_college import AttendanceHeatmapCollege
from app.schemas.department_attendance_snapshot import DepartmentAttendanceSnapshot
from app.schemas.subject_attendance_roster import SubjectAttendanceRoster
from app.schemas.teacher_subject_summary import TeacherSubjectSummary
from app.schemas.subject_session_stats import SubjectSessionStats
from app.schemas.student_risk_summary import StudentRiskSummary
from app.schemas.session import Session



# Global client and db
client: Optional[AsyncIOMotorClient] = None
db = None

async def init_db():
    global client, db

    client = AsyncIOMotorClient(settings.MONGO_URI)

    db_name = settings.MONGO_DB_NAME or settings.MONGO_URI.split("/")[-1].split("?")[0]
    db = client[db_name]

    document_models = [
        Student,
        Teacher,
        Clerk,
        Subject,
        Attendance,
        ExceptionSession,
        StudentAttendanceSummary,
        AttendanceHeatmapCollege,
        DepartmentAttendanceSnapshot,
        SubjectAttendanceRoster, 
        TeacherSubjectSummary,
        SubjectSessionStats,  
        StudentRiskSummary,
        Session



    ]

    await init_beanie(database=db, document_models=document_models)
    print(f"✅ Database '{db_name}' connected successfully!")

async def close_db():
    if client:
        client.close()

def get_db():
    if db is None:
        raise RuntimeError("Database not initialized")
    return db
