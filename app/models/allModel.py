from pydantic import BaseModel, EmailStr,Field ,field_validator , HttpUrl
from enum import Enum
from app.schemas.timetable import Session,Timetable
from typing import Optional, List , Dict
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form 
from typing import Optional
import re
from datetime import datetime , date
from bson.objectid import ObjectId

class StudentRegisterRequest(BaseModel):
    first_name: str 
    middle_name: Optional[str] = None
    last_name: str 
    email: EmailStr 
    password: str = Field(..., min_length=6, max_length=6)  # Exactly 6 characters
    phone: str= Field(..., min_length=10, max_length=10)
    dob: date 
    roll_number: int
    program: str 
    department: str
    semester: int 
    batch_year: int 

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

class ResetPasswordRequest(BaseModel):
    email: str
    role : str
    otp: str
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
    phone: Optional[str] = None 
    dob: Optional[date] = None 



class SessionRequest(BaseModel):
    start_time: str = Field(...)  # Format: "HH:MM"
    end_time: str = Field(...)    # Format: "HH:MM"
    subject: str = Field(...)     # ObjectId as string for subject reference

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time_format(cls, v):
        if not isinstance(v, str) or v.count(":") != 1:
            raise ValueError("Time must be in HH:MM format")
        try:
            hours, minutes = map(int, v.split(":"))
            if not (0 <= hours <= 23 and 0 <= minutes <= 59):
                raise ValueError("Invalid time value")
        except ValueError:
            raise ValueError("Invalid time format")
        return v

    @field_validator("end_time")
    @classmethod
    def validate_time_order(cls, end_time, values):
        if "start_time" in values.data:
            start = datetime.strptime(values.data["start_time"], "%H:%M")
            end = datetime.strptime(end_time, "%H:%M")
            if end <= start:
                raise ValueError("End time must be after start time")
        return end_time

    @field_validator("subject")
    @classmethod
    def validate_subject_id(cls, v):
        try:
            ObjectId(v)  # Validate that the subject is a valid ObjectId string
        except Exception:
            raise ValueError("Subject must be a valid ObjectId")
        return v

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

# Pydantic model for TimetableRequest
class TimetableRequest(BaseModel):
    academic_year: str = Field(...)
    department: str = Field(...)
    program: str = Field(...)
    semester: str = Field(...)
    schedule: Dict[str, List[SessionRequest]] = {
        "Monday": [], "Tuesday": [], "Wednesday": [],
        "Thursday": [], "Friday": [], "Saturday": [], "Sunday": []
    }

    @field_validator("academic_year")
    @classmethod
    def validate_academic_year(cls, v):
        if not re.match(r"^\d{4}", v):
            raise ValueError("Academic year must be in YYYY format")
        return v

    class Config:
        arbitrary_types_allowed = True


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
    department: str
    program: str
    semester: int
    batch_year: int
    roll_number: int
    profile_picture: Optional[HttpUrl] = None
    profile_picture_id: Optional[str] = None
    subjects_assigned: List[SubjectShortView] = []

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            datetime: lambda dt: dt.isoformat(),
            ObjectId: str
        }