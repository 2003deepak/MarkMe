from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from app.models.allModel import AttendanceStudentRequest, NotificationRequest, StudentListingView
from app.schemas.attendance import Attendance
from datetime import datetime

from app.schemas.student import Student
from app.services.common_services.notify_users import notify_users

async def mark_student_attendance(request: Request, attendance_request: AttendanceStudentRequest):

    # Step 1: Verify teacher
    user_role = request.state.user.get("role")
    if user_role != "teacher":
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Only teachers can mark attendance"}
        )

    # Step 2: Fetch Attendance + shallow links
    try:
        attendance_record = await Attendance.get(
            attendance_request.attendance_id,
            fetch_links=True,
            nesting_depth=3
        )

        if not attendance_record:
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": "Attendance record not found"}
            )

    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": f"Invalid attendance ID: {str(e)}"}
        )


    current_time = datetime.now().time()
    current_date = datetime.now().date()

    # Identify session type
    if attendance_record.session:
        session = attendance_record.session
        is_exception = False

    elif attendance_record.exception_session:
        exception = attendance_record.exception_session
        session = exception.session

        if not session:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "Invalid exception session → missing session reference"}
            )

        is_exception = True

    else:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "No session or exception session found"}
        )

    # Validate teacher
    if not session.teacher:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Teacher details not found for this session"}
        )

    if str(session.teacher.id) != str(request.state.user.get("id")):
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Teacher not authorized for this session"}
        )

    # Validate class date
    if is_exception:
        if attendance_record.exception_session.date.date() != current_date:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "Attendance can only be marked on the exception session date"}
            )
    else:
        if session.day.lower() != current_date.strftime("%A").lower():
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "Attendance cannot be marked on a different day"}
            )

    # Validate time window
    try:
        if is_exception:
            start = datetime.strptime(attendance_record.exception_session.start_time, "%H:%M").time()
            end = datetime.strptime(attendance_record.exception_session.end_time, "%H:%M").time()
        else:
            start = datetime.strptime(session.start_time, "%H:%M").time()
            end = datetime.strptime(session.end_time, "%H:%M").time()
    except ValueError:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Invalid time format in session"}
        )

    if not (start <= current_time <= end):
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Attendance can only be marked within session time"}
        )

    # Validate binary string
    if not isinstance(attendance_request.attendance_student, str) or \
            not set(attendance_request.attendance_student) <= {"0", "1"}:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Attendance must be a binary string of 0 and 1"}
        )
        
    # Fetching fcm token of present and absent student based on bit string 
    program = session.program 
    batch_year = session.academic_year
    department = session.department 
    semester = session.semester
    
    print(program , batch_year , department , semester)
    
    
    students = await Student.find_many(
            Student.program == program,
            Student.semester == int(semester),
            Student.department == department,
            Student.batch_year == int(batch_year)
        ).project(StudentListingView).sort("roll_no").to_list()
    
    print(len(students))
    
    # Safety check
    if len(attendance_request.attendance_student) != len(students):
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "Attendance string length does not match number of students"
            }
        )

    present_students = []
    absent_students = []

    for idx, bit in enumerate(attendance_request.attendance_student):
        student = students[idx]
        student_id = str(student.student_id)

        if bit == "1":
            present_students.append(student_id)
        else:
            absent_students.append(student_id)
    
    


  
    # Save attendance
    try:
        attendance_record.students = attendance_request.attendance_student
        await attendance_record.save()
        
        # Send Confirmation Notification to the student 
        await notify_users(
            NotificationRequest(
                user="student",
                target_ids=present_students,
                title="Attendance Marked",
                message=f"Your attendance has been marked present for session on {current_date}.",
                data=None
            )
        )


        # Send Absence Notification to absent students
        await notify_users(
            NotificationRequest(
            user="student",
            target_ids=absent_students,
            title="Lecture Missed",
            message=f"Your attendance has been marked absent for session on {current_date}. If you feel this is an error, please contact your teacher."
            )
        )

        
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"Failed to update attendance: {str(e)}"}
        )

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "Attendance marked successfully",
            "data": {"attendance_id": attendance_request.attendance_id}
        }
    )
