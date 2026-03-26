from fastapi import Request
from fastapi.responses import JSONResponse
from datetime import datetime, date
from bson import ObjectId

from app.models.allModel import (
    AttendanceStudentRequest,
    NotificationRequest,
    StudentListingView
)
from app.schemas.attendance import Attendance
from app.schemas.student import Student
from app.services.common_services.notify_users import notify_users


async def update_student_attendance(
    request: Request,
    attendance_request: AttendanceStudentRequest
):

    # auth
    user = request.state.user
    role = user.get("role")

    if role not in ["teacher", "clerk"]:
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Access denied"}
        )

    # binary validation
    new_binary = attendance_request.attendance_student
    if not isinstance(new_binary, str) or not set(new_binary) <= {"0", "1"}:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Attendance must be binary string"}
        )

    # aggregation
    pipeline = [
        {"$match": {"_id": ObjectId(attendance_request.attendance_id)}},

        {
            "$lookup": {
                "from": "sessions",
                "localField": "session.$id",
                "foreignField": "_id",
                "as": "session_data"
            }
        },
        {
            "$lookup": {
                "from": "exception_sessions",
                "localField": "exception_session.$id",
                "foreignField": "_id",
                "as": "exception_session_data"
            }
        },
        {"$unwind": {"path": "$session_data", "preserveNullAndEmptyArrays": True}},
        {"$unwind": {"path": "$exception_session_data", "preserveNullAndEmptyArrays": True}},

        {
            "$lookup": {
                "from": "sessions",
                "localField": "exception_session_data.session.$id",
                "foreignField": "_id",
                "as": "exception_session_actual"
            }
        },
        {"$unwind": {"path": "$exception_session_actual", "preserveNullAndEmptyArrays": True}},
    ]

    docs = await Attendance.aggregate(pipeline).to_list()
    
    if not docs:
        return JSONResponse(
            status_code=404,
            content={"success": False, "message": "Attendance not found"}
        )

    attendance_doc = docs[0]

    # effective session
    session = (
        attendance_doc.get("exception_session_actual")
        or attendance_doc.get("session_data")
    )

    if not session:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Session resolution failed"}
        )

    old_binary = attendance_doc.get("students", "")
    
    print("Old Binary:", old_binary)
    print("New Binary:", new_binary)

    if len(old_binary) != len(new_binary):
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Attendance length mismatch"}
        )

    # clerk rules
    if role == "clerk":
        
        
        scopes = user.get("academic_scopes", [])

        allowed = any(
            scope["program_id"] == session.get("program") and
            scope["department_id"] == session.get("department")
            for scope in scopes
        )

        if not allowed:
            return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "message": "You are not authorized for this academic scope"
                }
            )

    # teacher rules
    if role == "teacher":
        teacher_ref = session.get("teacher")
        if not teacher_ref or str(teacher_ref.id) != user.get("id"):
            return JSONResponse(
                status_code=403,
                content={"success": False, "message": "You are not authorized to update this attendance"}
            )

            

        if attendance_doc["date"].date() != date.today():
            
            print(attendance_doc["date"].date() , date.today()) 
            return JSONResponse(
                status_code=403,
                content={"success": False, "message": "Updating Attendance allowed only for sessions held today"}
            )

    # fetch students
    students = await Student.find_many(
        Student.program == session["program"],
        Student.department == session["department"],
        Student.semester == int(session["semester"]),
        Student.batch_year == int(session["academic_year"]),
    ).project(StudentListingView).sort("roll_no").to_list()

    if len(students) != len(new_binary):
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Student count mismatch"}
        )

    # detect changes
    newly_present = []
    newly_absent = []

    for idx, (old_bit, new_bit) in enumerate(zip(old_binary, new_binary)):
        if old_bit == new_bit:
            continue

        student_id = str(students[idx].student_id)

        if old_bit == "0" and new_bit == "1":
            newly_present.append(student_id)
        elif old_bit == "1" and new_bit == "0":
            newly_absent.append(student_id)

    # update db
    await Attendance.find_one(
        Attendance.id == ObjectId(attendance_request.attendance_id)
    ).update(
        {"$set": {"students": new_binary, "updated_at": datetime.utcnow()}}
    )

    session_date = attendance_doc["date"].strftime("%d %b %Y")

    # notifications
    if newly_present:
        await notify_users(
            NotificationRequest(
                user="student",
                target_ids=newly_present,
                title="Attendance Updated",
                message=f"You were marked PRESENT for the session on {session_date}.",
                data=None
            )
        )

    if newly_absent:
        await notify_users(
            NotificationRequest(
                user="student",
                target_ids=newly_absent,
                title="Attendance Updated",
                message=f"You were marked ABSENT for the session on {session_date}.",
                data=None
            )
        )

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "message": "Attendance updated successfully",
            "data": {
                "attendance_id": attendance_request.attendance_id,
                "present_notified": len(newly_present),
                "absent_notified": len(newly_absent)
            }
        }
    )
