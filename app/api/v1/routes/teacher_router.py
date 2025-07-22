from fastapi import APIRouter, Form, UploadFile, File, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import ValidationError, BaseModel
from typing import List, Optional
from datetime import date
import json
from app.middleware.is_logged_in import is_logged_in
from app.services.teacher_services.get_teacher_detail import get_teacher_me
from app.services.teacher_services.update_teacher_profile import update_teacher_profile
from app.models.allModel import UpdateProfileRequest

# -- Pydantic Model Import

router = APIRouter()
security = HTTPBearer()  # Define security scheme




@router.get("/me")
async def get_teacher_me_route(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
    return await get_teacher_me(user_data)





@router.put("/me/update-profile")
async def update_teacher_profile_route(

    first_name: Optional[str] = Form(None),
    middle_name: Optional[str] = Form(None),
    last_name: Optional[str] = Form(None),
    mobile_number: Optional[str] = Form(None),
    profile_picture: Optional[UploadFile] = File(None),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):
    try:
        request_data = UpdateProfileRequest(
            first_name=first_name,
            middle_name=middle_name,
            last_name=last_name,
            phone=mobile_number,
        )
        return await update_teacher_profile(request_data, user_data, profile_picture)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=json.loads(e.json()))
    


# Fetch the current session for the logged-in teacher

# 1. Verify that the user has the role "teacher"
# 2. Extract current teacher email from the logged-in user
# 3. From the subject collection, find all subjects taught by this teacher (by email)
# 4. From the attendance DB, fetch the session where:
#    - subject_id matches one of teacher’s subjects
#    - date == today
#    - current_time is between start_time and end_time
# 5. Return the session if found; otherwise []


# @router.get("/session/current")
# async def get_current_session():
#     try:
        
        
#     except ValidationError as e:
#         raise HTTPException(status_code=422, detail=json.loads(e.json()))




# ✅ This API should be a websocket
# 🔐 Verify that the user has the role "teacher"
# 🖼️ Receive the classroom image from the client
# 🧠 Send the class image to the `face_queue` for processing
#    (Refer to register.py where a job was added to the queue using send_to_queue)
#
# 📤 The WebSocket should gradually return the recognized students in this format:
# {
#     "status": "progress",
#     "recognized": [
#         { "roll": "CS23-001", "name": "Aman" }
#     ]
# }
#
# {
#     "status": "progress",
#     "recognized": [
#         { "roll": "CS23-002", "name": "Sneha" }
#     ]
# }
#
# ✅ When all students are processed, send the final response:
# {
#     "status": "complete",
#     "annotated_image": "<base64-encoded-image>"
# }
#
# 📝 Example of how to push a task to the queue (reuse this pattern):
#
#     await send_to_queue("email_queue", {
#         "type": "send_email",
#         "data": {
#             "to": student_data.email,
#             "subject": "Welcome to MarkMe!",
#             "body": f"Hello {student_data.first_name}, your registration is successful!"
#         }
#     }, priority=5)  # Medium priority for email
#
# Replace this with:
#
#     await send_to_queue("face_queue", {
#         "type": "recognize_faces",
#         "data": {
#             "session_id": session_id,
#             "teacher_email": current_user.email,
#             "image_base64": "<classroom-image>"
#         }
#     }, priority=10)

# ✅ Sample success flow:
#     1. Client connects
#     2. Sends base64 image
#     3. Receives gradual progress results
#     4. Receives final annotated image
#
# 📦 Make sure to integrate annotation logic from the other Git repo into this flow

# Once the face recogniton work is added to the queue , in the file worker_face_recogniton , integrate the logic 
# of the file ( given by me in the other repo )

# @router.websocket("/session/recognize/{session_id}")
# async def recognize_students_websocket(websocket: WebSocket, session_id: str):


# In this API, return the full class list for the teacher’s current session
# Endpoint: GET /student/search

# 1. Ensure that the user is logged in and role = teacher

# 2. From the session context (subject_id), get the subject details
#    → Use subject_id (saved in the Attendance)
#    → From that subject document, fetch: 
#         - program_id
#         - department_id
#         - semester

# 3. Query the student collection where:
#      - student.program_id == subject.program_id
#      - student.department_id == subject.department_id
#      - student.semester == subject.semester

# 4. Return the list of matching students
#     → Each student should include at least: name, roll number, email (optional)

# 5. If no students are found, return an empty array

# @router.get("/student/search")




# In this API, mark the attendance for the session using bitmasking

# 1. Ensure that the logged-in user has the role 'teacher'

# 2. From the session_id, get the timetable info (to fetch list of students)
#    → This gives total number of students and their roll numbers

# 3. From the request body, you can expect a JSON like this:
#    [
#      { "name": "Rahul", "rollno": 23 },
#      { "name": "Indar", "rollno": 29 }
#    ]
#    → This represents the list of present students

# 4. Generate the attendance bitmask as a string:
#    → Length of bitmask = highest roll number (or fixed class size from timetable)
#    → Initialize all bits to '0'
#    → For each student in the input list, mark '1' at index (rollno - 1)
#       (Note: 0-based indexing — so roll no 69 sets bit at index 68)

# 5. Create the final attendance document:
#    {
#      "timetable_id": ...,
#      "subject_id": ...,
#      "teacher_id": ...,
#      "date": today (date only),
#      "day": current day string ("Monday", etc),
#      "slot_index": ...,
#      "attendance_mask": "100101001...01"
#    }

# 6. Save this document to the attendance collection in the DB

# 7. Add an empty placeholder (TODO) for notifying students who were absent
#    → After saving attendance, you can later publish a message or trigger notification

# @router.post("/session/markAttendance/{session_id}")
# async def create_Session(
#     credentials: HTTPAuthorizationCredentials = Depends(security),
#     user_data: dict = Depends(is_logged_in)
# ):
#     return await get_teacher_me(user_data)





# Injamul Your Work 

# In this route , it is used to add/cancel/reschedule a session for the teacher
# Ask for the timetable_id , date , action (Cancel, Rescheduled, Add)
# The payload data will change based on the action
# If action is Cancel, then slotReference is required
# If action is Rescheduled, then slotReference and newSlot are required
# No fixed structure for the payload, it will change based on the action
# Try to do it in JSON or basic form data using Form 

# Note : Currently work only for the action Cancel and Rescheduled , pass for the action Add
    
# Payload Structure for Action Cancel :-

# {
#   "timetable_id": "68679bca26d91dfb7170c560",
#   "date": "2025-07-25T00:00:00",
#   "action": "Cancel",
#   "slotReference": {
#     "day": "Monday",
#     "slotIndex": 1
#   }
# } 

# Payload Structure for Action Rescheduled :-

# {
#   "timetable_id": "68679bca26d91dfb7170c560",
#   "date": "2025-07-25T00:00:00",
#   "action": "Rescheduled",
#   "slotReference": {
#     "day": "Monday",
#     "slotIndex": 1
#   },
#   "newSlot": {
#     "startTime": "10:00",
#     "endTime": "11:00",
#     "subject": "Maths"
#   }
# }


# Do proper validation for the payload
# If the time_table_id is not present in the database or redis , return proper error
# If the new subject id is having issue , handle that 


# Once data is prepared add to exception_sessions collection in the database
# You can refer to the ExceptionSession Schema class in exception_session.py for the structure


# @router.post("/exception_session/create")
# # async def create_Session(
# #     credentials: HTTPAuthorizationCredentials = Depends(security),
# #     user_data: dict = Depends(is_logged_in)
# # ):
# #     return await get_teacher_me(user_data)