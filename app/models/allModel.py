from pydantic import BaseModel, EmailStr,Field ,field_validator
from enum import Enum
from app.schemas.timetable import Session,Timetable
from typing import Optional, List , Dict
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from typing import Optional
import re
from datetime import date , date

class StudentRegisterRequest(BaseModel):
    first_name: str 
    middle_name: Optional[str] = None
    last_name: str 
    email: EmailStr 
    password: str = Field(..., min_length=6, max_length=6)  # Exactly 6 characters
    phone: int 
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

class ResetPasswordRequest(BaseModel):
    email: str
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

class Component(BaseModel):
    type: str  # "Lecture", "Lab", etc.

class CreateSubjectRequest(BaseModel):
    subject_code: str 
    subject_name: str 
    department: str
    semester: int
    program: str
    components: List[Component]
    credit: int 


class ChangePasswordRequest(BaseModel):
    current_password : str 
    new_password : str
    email : EmailStr

class UpdateProfileRequest(BaseModel):
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None 
    dob: Optional[str] = None 


class SessionRequest(BaseModel):
    start_time: str
    end_time: str
    subject: str
    component: str 

   
class TimetableRequest(BaseModel):
    academic_year: str
    department: str
    program: str
    semester: str
    schedule: Dict[str, List[SessionRequest]] = {
        "Monday": [], "Tuesday": [], "Wednesday": [], 
        "Thursday": [], "Friday": [], "Saturday": [], "Sunday": []
    }