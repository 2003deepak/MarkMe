from app.models.allModel import NotificationRequest, StudentListingView
from app.schemas.session import Session
from app.schemas.student import Student
from app.services.common_services.notify_users import notify_users


async def notify_students_by_session(session: Session, title: str, message: str):
    students = await Student.find(
        Student.department == session.department,
        Student.program == session.program,
        Student.semester == session.semester,
        Student.batch_year == session.academic_year
    ).project(StudentListingView).to_list()

    student_ids = [str(s.student_id) for s in students]

    if not student_ids:
        return

    await notify_users(
        NotificationRequest(
            user="student",
            target_ids=student_ids,
            title=title,
            message=message,
        )
    )


async def notify_students_for_two_sessions(
    session_a: Session,
    session_b: Session,
    title: str,
    message: str
):
    affected = set()

    students_a = await Student.find(
        Student.department == session_a.department,
        Student.program == session_a.program,
        Student.semester == session_a.semester,
        Student.batch_year == session_a.academic_year
    ).project(StudentListingView).to_list()

    for s in students_a:
        affected.add(str(s.student_id))

    students_b = await Student.find(
        Student.department == session_b.department,
        Student.program == session_b.program,
        Student.semester == session_b.semester,
        Student.batch_year == session_b.academic_year
    ).project(StudentListingView).to_list()

    for s in students_b:
        affected.add(str(s.student_id))

    if not affected:
        return

    await notify_users(
        NotificationRequest(
            user="student",
            target_ids=list(affected),
            title=title,
            message=message,
        )
    )

