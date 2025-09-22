from pydantic import BaseModel, EmailStr,Field ,field_validator , HttpUrl , validator, ValidationInfo
from enum import Enum
from typing import Optional, List , Dict
from typing import Optional,List, Literal
import re
from datetime import datetime , date , time
from bson.objectid import ObjectId
from beanie import PydanticObjectId

class StudentRegisterRequest(BaseModel):
    first_name: str 
    last_name: str 
    email: EmailStr 
    password: str = Field(..., min_length=6, max_length=6)  # Exactly 6 characters

class TeacherRegisterRequest(BaseModel):
    first_name: str
    middle_name: Optional[str] = None
    last_name: str 
    email: EmailStr
    mobile_number: int
    department: str
    subjects_assigned: List[str] = []

  

class LoginRequest(BaseModel):
    email: EmailStr
    password: str 
    role: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr
    role: str

class OtpRequest(BaseModel):
    email: EmailStr
    role: Literal["student", "teacher", "clerk"]
    otp: str

class ResetPasswordRequest(BaseModel):
    email: str
    role : Literal["student", "teacher", "clerk"]
    new_password: str = Field(..., min_length=6, max_length=6)  # Exactly 6 characters

class CreateClerkRequest(BaseModel):
    first_name: str 
    middle_name: Optional[str] = None
    last_name: str 
    email: EmailStr
    mobile_number: int
    department: str
    program : str



class CreateSubjectRequest(BaseModel):
    subject_code: str 
    subject_name: str 
    department: str
    semester: int
    program: str
    component: str
    credit: int 


class ChangePasswordRequest(BaseModel):
    current_password : str 
    new_password : str

class UpdateProfileRequest(BaseModel):
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    dob: Optional[date] = None
    roll_number: Optional[int] = None
    program: Optional[str] = None
    department: Optional[str] = None
    semester: Optional[int] = None
    batch_year: Optional[int] = None



# Day of week type
DayOfWeek = Literal[
    "Monday", "Tuesday", "Wednesday",
    "Thursday", "Friday", "Saturday", "Sunday"
]

class ScheduleEntry(BaseModel):
    start_time: str = Field(..., pattern=r"^([01]\d|2[0-3]):([0-5]\d)$")
    end_time: str = Field(..., pattern=r"^([01]\d|2[0-3]):([0-5]\d)$")
    subject: PydanticObjectId  # Only subject ID is passed

    @field_validator("end_time")
    @classmethod
    def validate_end_after_start(cls, v: str, info) -> str:
        start = info.data.get("start_time")
        if start and v <= start:
            raise ValueError("end_time must be after start_time")
        return v


class TimeTableRequest(BaseModel):
    academic_year: str = Field(..., pattern=r"^\d{4}$")
    department: str = Field(..., min_length=2, max_length=50)
    program: str = Field(..., min_length=2, max_length=50)
    semester: str = Field(..., pattern=r"^(1|2|3|4|5|6|7|8)$")

    schedule: Dict[DayOfWeek, List[ScheduleEntry]] = Field(
        ..., description="Map of weekday to list of sessions"
    )

    @field_validator("schedule")
    @classmethod
    def validate_schedule_days(cls, v: Dict[str, List[ScheduleEntry]]) -> Dict[str, List[ScheduleEntry]]:
        allowed = {
            "Monday", "Tuesday", "Wednesday",
            "Thursday", "Friday", "Saturday", "Sunday"
        }
        invalid = set(v.keys()) - allowed
        if invalid:
            raise ValueError(f"Invalid days: {invalid}")
        return v

    @field_validator("schedule")
    @classmethod
    def validate_no_overlap(cls, v: Dict[str, List[ScheduleEntry]]) -> Dict[str, List[ScheduleEntry]]:
        def to_minutes(t: str) -> int:
            h, m = map(int, t.split(":"))
            return h * 60 + m

        for day, sessions in v.items():
            if len(sessions) < 2:
                continue
            sorted_sessions = sorted(sessions, key=lambda s: s.start_time)
            for i in range(1, len(sorted_sessions)):
                if to_minutes(sorted_sessions[i].start_time) < to_minutes(sorted_sessions[i-1].end_time):
                    raise ValueError(f"Overlapping sessions on {day}")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "academic_year": "2025",
                "department": "BTECH",
                "program": "MCA",
                "semester": "2",
                "schedule": {
                    "Monday": [
                        {
                            "start_time": "08:00",
                            "end_time": "09:30",
                            "subject": "688746daa94ba4fa2636105a"
                        },
                        {
                            "start_time": "09:30",
                            "end_time": "11:00",
                            "subject": "688791f8692063b616d9cdcf"
                        }
                    ],
                    "Tuesday": [],
                    "Sunday": []
                }
            }
        }
    }


class ClassSearchRequest(BaseModel):
    batch_year: int
    program: str
    semester: int

class CreateExceptionSession(BaseModel):
    session_id: Optional[str] = None
    date: date
    action: str

    # Only needed for Add / Reschedule
    new_start_time: Optional[str] = None
    new_end_time: Optional[str] = None
   


# Projection Models 

class ClerkShortView(BaseModel):
    email : str
    first_name : str
    last_name : str
    middle_name : Optional[str]
    department: str
    program: str
    phone : int
    profile_picture : Optional[str] 

class SubjectOutputDetail(BaseModel):
    subject_code: str
    subject_name: str
    component: str

class TeacherShortView(BaseModel):
   
    teacher_id: str
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    email: EmailStr
    mobile_number: Optional[int] = None # Ensure default is None for Optional
    department: str
    profile_picture: Optional[HttpUrl] = None
    profile_picture_id: Optional[str] = None # Make sure this is also handled

    subjects_assigned: List[SubjectOutputDetail] = []

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda dt: dt.isoformat(),
           
        }

class TeacherShortViewForSubject(BaseModel):
   
    teacher_id: str
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    email: EmailStr
    department: str
    profile_picture: Optional[HttpUrl] = None
    profile_picture_id: Optional[str] = None # Make sure this is also handled


    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda dt: dt.isoformat(),
           
        }

class SubjectShortView(BaseModel):
    subject_code: str
    subject_name: str
    department: str
    semester: int
    program: str
    component: str
    credit: int
    teacher_assigned: Optional[TeacherShortViewForSubject] = None  

    class Config:
        arbitrary_types_allowed = True  # Allow ObjectId type
        json_encoders = {
            ObjectId: str  # Serialize ObjectId to string in API responses
        }

class StudentShortView(BaseModel):
    student_id: str
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    email: EmailStr
    phone: Optional[str] = None
    department: Optional[str] = None
    program: Optional[str] = None
    semester: Optional[int] = None
    batch_year: Optional[int] = None
    roll_number: Optional[int] = None
    profile_picture: Optional[HttpUrl] = None
    is_verified: Optional[bool] = None

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            datetime: lambda dt: dt.isoformat(),
            ObjectId: str
        }
        
class VerifyEmailRequest(BaseModel):
    token: str
    
class UpdateClerkRequest(BaseModel):
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[int] = None
    department: Optional[str] = None
    program: Optional[str] = None

    @validator("department", "program")
    def check_non_empty(cls, v):
        if v is not None and v.strip() == "":
            raise ValueError(f"{cls.__name__} cannot be empty")
        return v
    

class SessionShortView(BaseModel):
    session_id: str
    start_time: str
    end_time: str
    subject_name: str
    teacher_name: str

    @field_validator("start_time", "end_time")
    def validate_time_format(cls, v, info: ValidationInfo):
        if not re.match(r"^\d{2}:\d{2}$", v):
            raise ValueError(f"{info.field_name} must be in HH:MM format")
        return v

class DaySchedule(BaseModel):
    day: str
    sessions: List[SessionShortView]

    @field_validator("day")
    def validate_day(cls, v, info: ValidationInfo):
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        if v not in days:
            raise ValueError(f"{info.field_name} must be one of: Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday")
        return v

class TimeTableResponse(BaseModel):
    program: str
    department: str
    semester: str
    academic_year: str
    schedule: List[DaySchedule]

    @field_validator("program", "department")
    def check_non_empty(cls, v, info: ValidationInfo):
        if not v.strip():
            raise ValueError(f"{info.field_name} cannot be empty")
        return v

    @field_validator("semester")
    def check_semester_range(cls, v, info: ValidationInfo):
        try:
            semester = int(v)
            if not (1 <= semester <= 8):
                raise ValueError(f"{info.field_name} must be between 1 and 8")
        except ValueError:
            raise ValueError(f"{info.field_name} must be a valid integer")
        return v

    @field_validator("academic_year")
    def check_academic_year(cls, v, info: ValidationInfo):
        try:
            year = int(v)
            current_year = datetime.utcnow().year
            if not (2000 <= year <= current_year + 1):
                raise ValueError(f"{info.field_name} must be between 2000 and {current_year + 1}")
        except ValueError:
            raise ValueError(f"{info.field_name} must be a valid integer")
        return v