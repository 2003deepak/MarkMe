import asyncio
from beanie.operators import Set
from app.core.database import init_db
from app.schemas.attendance import Attendance
from app.schemas.student import Student
from app.schemas.student_attendance_summary import StudentAttendanceSummary
from app.schemas.session import Session
from bson import DBRef, ObjectId


async def handle_attendance_update(att: Attendance, is_insert: bool = False):
    students_bitstr = att.students
    n_students = len(students_bitstr)

    # ✅ Fetch all students in roll order
    student_list = await Student.find(
        {"program": "MCA", "semester": 2}
    ).sort("roll_no").to_list()

    if len(student_list) + 1 != n_students:
        print(f"⚠️ Mismatch: Attendance has {n_students} bits, but {len(student_list)} students found")
        return

    # ✅ Fetch linked session document
    session: Session = await att.session.fetch()
    if not session:
        print(f"⚠️ Session not found for Attendance: {att.id}")
        return

    # ✅ Fetch linked subject if necessary (assuming session.subject is a Link[Subject])
    if hasattr(session, 'subject') and session.subject:
        subject = await session.subject.fetch()
        if not subject:
            print(f"⚠️ Subject not found for Session: {session.id}")
            return
        subject_id = subject.id
    else:
        print(f"⚠️ No subject linked to Session: {session.id}")
        return

    # Loop over each student and update their summary
    for i, student in enumerate(student_list):
        is_present = students_bitstr[i] == "1"

        # Find existing summary
        summary = await StudentAttendanceSummary.find_one(
            {
                "student": DBRef("students", ObjectId(student.id)),
                "subject": DBRef("subjects", ObjectId(subject_id)),
            }
        )

        if not summary:
            # Create a new summary if it doesn't exist
            print(f"📝 Creating new StudentAttendanceSummary for student {student.id} and subject {subject_id}")
            summary = StudentAttendanceSummary(
                student=student.id,
                subject=subject_id,
                total_classes=0,
                attended=0,
                percentage=0.0,
                sessions_present=[]
            )
            await summary.insert()

        # Prepare update
        update_dict = {
            "attended": summary.attended + (1 if is_present else 0) if is_insert else (1 if is_present else 0),
            "sessions_present": (
                summary.sessions_present + [att.id]
                if is_present and att.id not in summary.sessions_present
                else summary.sessions_present
            )
        }

        # Only increment total_classes for new sessions (insert operations)
        if is_insert:
            update_dict["total_classes"] = summary.total_classes + 1
        else:
            update_dict["total_classes"] = summary.total_classes

        # Update percentage
        total = update_dict["total_classes"]
        attended = update_dict["attended"]
        update_dict["percentage"] = round((attended / total * 100) if total > 0 else 0.0, 2)

        # ✅ Update in DB
        await summary.update(Set(update_dict))
        print(f"✅ Updated StudentAttendanceSummary for student {student.id} and subject {subject_id}")

    print(f"✅ Processed updates for Attendance: {att.id}")


async def watch_attendance_changes():
    await init_db()

    collection = Attendance.get_motor_collection()
    # Watch for both insert and update operations
    pipeline = [{"$match": {"operationType": {"$in": ["insert", "update"]}}}]

    async with collection.watch(pipeline) as stream:
        async for change in stream:
            operation_type = change["operationType"]
            doc_id = change["documentKey"]["_id"]
            print(f"🔔 {operation_type.capitalize()} detected in Attendance doc: {doc_id}")

            if operation_type == "insert" or (
                operation_type == "update"
                and "students" in change.get("updateDescription", {}).get("updatedFields", {})
            ):
                attendance = await Attendance.get(doc_id)
                if attendance:
                    # Pass is_insert=True for insert operations, False for updates
                    await handle_attendance_update(attendance, is_insert=(operation_type == "insert"))


if __name__ == "__main__":
    asyncio.run(watch_attendance_changes())