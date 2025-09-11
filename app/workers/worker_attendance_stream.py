import asyncio
import logging
from typing import List, Tuple
from decimal import Decimal as PyDecimal
from beanie import Link
from beanie.operators import Set, AddToSet, Pull
from app.core.database import init_db
from bson import ObjectId, DBRef
from decimal import Decimal
from app.schemas.attendance import Attendance
from app.schemas.student_attendance_summary import StudentAttendanceSummary
from app.schemas.teacher_subject_summary import TeacherSubjectSummary
from app.schemas.student import Student
from app.schemas.session import Session
from app.schemas.exception_session import ExceptionSession
from app.schemas.teacher import Teacher
from app.schemas.subject import Subject

# Logger
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


#############################################
# 🧠 Bit-Diff Calculator
#############################################

def calculate_bit_changes(old_bitstr: str, new_bitstr: str) -> List[Tuple[int, bool, bool]]:
    """
    Returns list of tuples: (student_index, was_present, is_now_present)
    """
    old_bitstr = old_bitstr.strip() if old_bitstr else ""
    new_bitstr = new_bitstr.strip() if new_bitstr else ""

    max_len = max(len(old_bitstr), len(new_bitstr))
    changes = []

    for i in range(max_len):
        old_bit = old_bitstr[i] if i < len(old_bitstr) else "0"
        new_bit = new_bitstr[i] if i < len(new_bitstr) else "0"

        was_present = old_bit == "1"
        is_now_present = new_bit == "1"

        if was_present != is_now_present:
            changes.append((i, was_present, is_now_present))

    return changes


#############################################
# 🧩 Updater: Student Attendance Summary
#############################################

async def update_student_attendance_summary(
    attendance: Attendance,
    student: Student,
    subject: Link,
    was_present: bool,
    is_now_present: bool,
    is_initial_record: bool
):
    """
    Handles updates for StudentAttendanceSummary collection
    """
    try:
        summary = await StudentAttendanceSummary.find_one(
            StudentAttendanceSummary.student == DBRef("students", student.id),
            StudentAttendanceSummary.subject == DBRef("subjects", subject.id)
        )
    except Exception as e:
        logger.error(f"🚨 Error querying summary for student {student.id}, subject {subject.id}: {e}")
        return

    # Calculate deltas
    total_classes_delta = 1 if is_initial_record else 0
    attended_delta = 0

    if is_initial_record:
        attended_delta = 1 if is_now_present else 0
    else:
        if was_present and not is_now_present:
            attended_delta = -1
        elif not was_present and is_now_present:
            attended_delta = 1

    attendance_ref = DBRef("attendances", attendance.id)

    if not summary:
        # Create new summary
        total_classes = 1 if is_initial_record else 0
        attended = 1 if (is_initial_record and is_now_present) else 0
        percentage = round((attended / total_classes * 100) if total_classes > 0 else 0.0, 2)

        summary = StudentAttendanceSummary(
            student=student,
            subject=subject,
            total_classes=total_classes,
            attended=attended,
            percentage=percentage,
            sessions_present=[attendance.id] if is_now_present else [],
            created_at=attendance.created_at or None,
            updated_at=attendance.updated_at or None
        )
        try:
            await summary.insert()
            logger.info(f"📝 Created StudentAttendanceSummary for student {student.id}, subject {subject.id}")
        except Exception as e:
            logger.error(f"🚨 Error inserting summary for student {student.id}, subject {subject.id}: {e}")
    else:
        # Update existing summary
        new_total = summary.total_classes + total_classes_delta
        new_attended = max(0, summary.attended + attended_delta)
        new_percentage = round((new_attended / new_total * 100) if new_total > 0 else 0.0, 2)

        update_ops = [
            Set({
                StudentAttendanceSummary.total_classes: new_total,
                StudentAttendanceSummary.attended: new_attended,
                StudentAttendanceSummary.percentage: new_percentage,
                StudentAttendanceSummary.updated_at: attendance.updated_at or None,
            })
        ]

        if was_present and not is_now_present:
            update_ops.append(Pull({StudentAttendanceSummary.sessions_present: attendance_ref}))
        elif not was_present and is_now_present:
            update_ops.append(AddToSet({StudentAttendanceSummary.sessions_present: attendance_ref}))

        try:
            await summary.update(*update_ops)
            logger.info(f"✅ Updated StudentAttendanceSummary for student {student.id}, subject {subject.id}")
        except Exception as e:
            logger.error(f"🚨 Error updating summary for student {student.id}, subject {subject.id}: {e}")


#############################################
# 🧩 Updater: Teacher Subject Summary
#############################################

async def update_teacher_subject_summary(
    attendance: Attendance,
    teacher: Link,
    subject: Link,
    is_initial_record: bool
):
    """
    Updates TeacherSubjectSummary for the teacher-subject pair.
    Called ON EVERY attendance update.
    Only increments session count if initial record.
    Always recalculates category counts and rolling average.
    """
    try:
        # Find existing summary
        summary = await TeacherSubjectSummary.find_one(
            TeacherSubjectSummary.teacher == DBRef("teachers", teacher.id),
            TeacherSubjectSummary.subject == DBRef("subjects", subject.id)
        )

        # Calculate today’s attendance percentage
        bitstr = attendance.students or ""
        total_students = len(bitstr)
        present_count = bitstr.count("1")
        today_percentage = (present_count / total_students * 100) if total_students > 0 else 0.0


        # Initialize or update
        if not summary:
            # Create new summary
            new_total_sessions = 1
            new_avg_attendance = Decimal(str(today_percentage))

            # Fetch category counts
            defaulter_count, at_risk_count, top_performer_count = await get_attendance_category_counts(subject.id)

            summary = TeacherSubjectSummary(
                teacher=teacher,
                subject=subject,
                total_sessions_conducted=new_total_sessions,
                average_attendance_percentage=new_avg_attendance,
                defaulter_count=defaulter_count,
                at_risk_count=at_risk_count,
                top_performer_count=top_performer_count
            )
            await summary.insert()
            logger.info(f"📝 Created TeacherSubjectSummary for teacher {teacher.id}, subject {subject.id}")

        else:
            # Update existing — session count only if initial
            new_total_sessions = summary.total_sessions_conducted + (1 if is_initial_record else 0)

         
            if is_initial_record:
                # New session → bump count
                old_total = summary.total_sessions_conducted
                old_avg = summary.average_attendance_percentage  # already Decimal

                new_avg_attendance = ((old_avg * old_total) + Decimal(str(today_percentage))) / (old_total + 1)
                new_total_sessions = old_total + 1

            else:
                # Existing session updated → replace old % with new %
                old_total = summary.total_sessions_conducted
                old_avg = summary.average_attendance_percentage  # Decimal

                # You MUST fetch the actual old session percentage (not overall avg!)
                old_session_percentage = Decimal(str(attendance.average_attendance_percentage))  

                new_avg_attendance = ((old_avg * old_total) - old_session_percentage + Decimal(str(today_percentage))) / old_total
                new_total_sessions = old_total

            # ALWAYS recalculate category counts — student % may have changed!
            defaulter_count, at_risk_count, top_performer_count = await get_attendance_category_counts(subject.id)

            # Update all fields
            await summary.set({
                TeacherSubjectSummary.total_sessions_conducted: new_total_sessions,
                TeacherSubjectSummary.average_attendance_percentage: PyDecimal(str(round(new_avg_attendance, 2))),
                TeacherSubjectSummary.defaulter_count: defaulter_count,
                TeacherSubjectSummary.at_risk_count: at_risk_count,
                TeacherSubjectSummary.top_performer_count: top_performer_count
            })
            logger.info(f"✅ Updated TeacherSubjectSummary for teacher {teacher.id}, subject {subject.id}")

    except Exception as e:
        logger.error(f"🚨 Error in update_teacher_subject_summary for attendance {attendance.id}: {e}")


async def get_attendance_category_counts(subject_id: ObjectId) -> tuple[int, int, int]:
    """
    Returns (defaulter_count, at_risk_count, top_performer_count) for given subject.
    Based on StudentAttendanceSummary.percentage:
        - Defaulter: < 75%
        - At Risk: 75% <= x < 85%
        - Top Performer: >= 85%
    """
    try:
        summaries = await StudentAttendanceSummary.find(
            StudentAttendanceSummary.subject == DBRef("subjects", subject_id)
        ).to_list()

        defaulter = 0
        at_risk = 0
        top_performer = 0

        for s in summaries:
            pct = s.percentage
            if pct < 75.0:
                defaulter += 1
            elif 75.0 <= pct < 85.0:
                at_risk += 1
            elif pct >= 85.0:
                top_performer += 1

        return defaulter, at_risk, top_performer

    except Exception as e:
        logger.error(f"🚨 Error calculating category counts for subject {subject_id}: {e}")
        return 0, 0, 0


#############################################
# 🚦 Main Handler — Manual Ordered Execution
#############################################

async def handle_attendance_update(attendance: Attendance, old_bitstr: str, new_bitstr: str):
    # Normalize strings
    old_bitstr = old_bitstr.strip() if old_bitstr else ""
    new_bitstr = new_bitstr.strip() if new_bitstr else ""

    if old_bitstr == new_bitstr:
        logger.info(f"✅ No actual change in attendance bits for {attendance.id}")
        return

    logger.info(f"📊 Processing attendance update: {attendance.id}")
    logger.info(f"   Old: {old_bitstr}")
    logger.info(f"   New: {new_bitstr}")

    is_initial_record = not bool(old_bitstr) and bool(new_bitstr)
    logger.info(f"   Is initial record? {is_initial_record}")

    # Fetch all links
    try:
        await attendance.fetch_all_links()
    except Exception as e:
        logger.error(f"🚨 Error fetching links for attendance {attendance.id}: {e}")
        return

    # Resolve session context
    session = None
    if attendance.session:
        try:
            await attendance.session.fetch_all_links()
            session = attendance.session
        except Exception as e:
            logger.error(f"🚨 Error fetching session links: {e}")
            return
    elif attendance.exception_session:
        try:
            await attendance.exception_session.fetch_all_links()
            await attendance.exception_session.session.fetch_all_links()
            session = attendance.exception_session.session
        except Exception as e:
            logger.error(f"🚨 Error fetching exception session links: {e}")
            return
    else:
        logger.warning(f"⚠️ No session context for attendance {attendance.id}")
        return

    # Extract context: subject, program, department, semester, TEACHER
    try:
        await session.fetch_all_links()
        subject = session.subject
        program = session.program
        department = session.department
        semester = int(session.semester)
        teacher = session.teacher  # 👈 Ensure Session model has this field
    except Exception as e:
        logger.error(f"🚨 Error extracting session context: {e}")
        return

    if not all([program, semester, department, subject, teacher]):
        logger.warning(f"⚠️ Missing context for attendance {attendance.id}")
        return

    # Fetch students
    try:
        student_list = await Student.find_many(
            Student.program == program,
            Student.semester == semester,
            Student.department == department
        ).sort("roll_no").to_list()
    except Exception as e:
        logger.error(f"🚨 Error fetching students: {e}")
        return

    if not student_list:
        logger.warning(f"⚠️ No students found")
        return

    if len(student_list) != len(new_bitstr):
        logger.warning(f"⚠️ Student count mismatch: {len(student_list)} vs {len(new_bitstr)} bits")
        return

    # Calculate changes
    changes = calculate_bit_changes(old_bitstr, new_bitstr)
    logger.info(f"🔄 Detected {len(changes)} student changes")

    # ✅ STEP 1: Update Student Attendance Summary (for each changed student)
    for index, was_present, is_now_present in changes:
        if index >= len(student_list):
            logger.warning(f"⚠️ Index {index} out of student list range")
            continue

        student = student_list[index]
        if not isinstance(student, Student):
            logger.error(f"⚠️ Invalid student at index {index}")
            continue

        try:
            await update_student_attendance_summary(
                attendance, student, subject, was_present, is_now_present, is_initial_record
            )
        except Exception as e:
            logger.error(f"🚨 Error in update_student_attendance_summary for student {student.id}: {e}")
            continue  # Don't block others

    # ✅ STEP 2: Update Teacher Subject Summary — ALWAYS, on every change
    try:
        await update_teacher_subject_summary(
            attendance, teacher, subject, is_initial_record
        )
    except Exception as e:
        logger.error(f"🚨 Error in update_teacher_subject_summary for attendance {attendance.id}: {e}")

    logger.info(f"✅ Processed {len(changes)} student(s) for Attendance {attendance.id}")


#############################################
# 👂 Change Stream Watcher
#############################################

async def watch_attendance_changes():
    logger.info("🚀 Initializing DB connection...")
    try:
        await init_db()
        logger.info("✅ Database connected.")
    except Exception as e:
        logger.error(f"🚨 Failed to initialize database: {e}")
        raise

    pipeline = [{"$match": {"operationType": "update"}}]
    collection = Attendance.get_motor_collection()

    logger.info("👂 Listening for updates on Attendance collection...")

    try:
        async with collection.watch(
            pipeline,
            full_document="updateLookup",
            full_document_before_change="required"
        ) as stream:
            async for change in stream:
                doc_id = change["documentKey"]["_id"]
                logger.info(f"🔔 Update detected: {doc_id}")

                new_doc = change.get("fullDocument")
                old_doc = change.get("fullDocumentBeforeChange")

                if not new_doc or not old_doc:
                    logger.warning(f"⚠️ Missing document data for {doc_id}")
                    continue

                new_bitstr = new_doc.get("students", "")
                old_bitstr = old_doc.get("students", "")

                try:
                    attendance = await Attendance.get(doc_id)
                    if not attendance:
                        logger.error(f"❌ Attendance {doc_id} not found")
                        continue

                    await handle_attendance_update(attendance, old_bitstr, new_bitstr)
                except Exception as e:
                    logger.error(f"🚨 Error processing update for {doc_id}: {e}")
                    continue

    except Exception as e:
        logger.error(f"🚨 Watch stream error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(watch_attendance_changes())