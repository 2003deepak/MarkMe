from fastapi import APIRouter, Form, UploadFile, File, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.services.student_services.get_student_detail import get_student_detail
from app.services.clerk_services.add_timetable import add_timetable
from pydantic import ValidationError, BaseModel
from app.middleware.is_logged_in import is_logged_in
from app.models.allModel import TimeTableRequest

router = APIRouter()
security = HTTPBearer()

@router.post("/create")
async def create_timetable(
    request: TimeTableRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_data: dict = Depends(is_logged_in)
):

    return await add_timetable(request, user_data)


# We need to implement the get_timetable_data function to retrieve timetable data for the MarkMeTest application.
# The function will be called by a GET endpoint and must be accessible to all logged-in users (teachers, admins, clerks, students).
# It should fetch sessions based on department, program, and semester, and return a JSON response with sessions grouped by day.
# Below are the detailed requirements for implementation.


# Requirements:
# 1. Accessibility:
#    - The function must be accessible to all authenticated users (teachers, admins, clerks, students).
#    - The user_data parameter, provided by the is_logged_in middleware, contains user information to verify authentication.

# 2. Input Parameters:
#    - The function accepts three parameters: department (e.g., "BTECH"), program (e.g., "MCA"), and semester (e.g., "2").
#    - These parameters are used to filter sessions from the Session collection in the database.

# 3. Database Schema Reference:
#    - The Session collection stores timetable data with the following structure:
#     
#      {
#          "_id": "6893b8c76200d14582a3349f",
#          "day": "Monday",
#          "start_time": "08:00",
#          "end_time": "23:00",
#          "subject": DBRef('subjects', '688746daa94ba4fa2636105a'),
#          "teacher": DBRef('teachers', '688749d5a94ba4fa2636105c'),
#          "academic_year": "2025",
#          "department": "BTECH",
#          "program": "MCA",
#          "semester": "2",
#          "created_at": "2025-08-06T20:19:19.325+00:00"
#      }
#    
#    - Note: The subject and teacher fields are DBRef objects referencing the subjects and teachers collections.

# 4. Data Fetching:
#    - Use Beanie's ORM to query the Session collection based on department, program, and semester.
#    - Utilize fetch_links() to resolve the DBRef fields (subject and teacher) and retrieve the linked data (e.g., subject name, teacher name).
#    - Refer to the Beanie documentation for proper usage of fetch_links().
#    - Use a projection model (e.g., SessionShortView from app.models.allModel) to shape the fetched data, similar to:
#      ```python
#      student_dict = await Session.find_one()
#      student_out_data = SessionShortView.model_validate(student_dict)
#      ```

# 5. Response Format:
#    - The function must return a TimeTableResponse object with the following JSON structure:
#     
#      {
#          "program": "MCA",
#          "department": "BTECH",
#          "semester": "2",
#          "schedule": [
#              {"day": "Monday", "sessions": [
#                  {session_id "start_time": "08:00", "end_time": "09:00", "subject_name": "Subject Name", "teacher_name": "Teacher Name"},
#                  ...
#              ]},
#              {"day": "Tuesday", "sessions": [...]},
#              ...
#          ]
#      }
#      ```
#    - Sessions should be grouped by day (Monday through Sunday).
#    - Only include days that have sessions in the schedule array.
#    - Sort sessions within each day by start_time for consistency.

# 6. Implementation Notes:
#    - Instead of storing sessions in a nested timetable format, sessions are stored per day with start_time and end_time.
#    - Ensure the response adheres to the TimeTableResponse Pydantic model for validation.
#    - Handle errors appropriately (e.g., invalid department, program, or semester) by raising HTTPException with a 400 or 500 status code.
#    - Refer to the SubjectShortView in app.models.allModel for guidance on using projection models with Beanie.


# @router.get("/get", response_model=TimeTableResponse)
# async def get_timetable(
#     department: str,
#     program: str,
#     semester: str,
#     credentials: HTTPAuthorizationCredentials = Depends(security),
#     user_data: dict = Depends(is_logged_in)
# ):

#     return await get_timetable_data(department, program, semester, user_data)

