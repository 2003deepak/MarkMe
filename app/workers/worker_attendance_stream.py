import asyncio
import logging
from datetime import date
from decimal import Decimal
from typing import List, Tuple, Optional
from decimal import Decimal as PyDecimal
from beanie import Link
from beanie.operators import Set, AddToSet, Pull
from app.core.database import init_db
from bson import ObjectId, DBRef
from decimal import Decimal
from app.schemas.attendance import Attendance
from app.schemas.student_attendance_summary import StudentAttendanceSummary
from app.schemas.teacher_subject_summary import TeacherSubjectSummary
from app.schemas.subject_session_stats import SubjectSessionStats
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
# 🧠 SMART Bit-Diff Calculator
#############################################

def calculate_bit_changes(old_bitstr: str, new_bitstr: str) -> Tuple[bool, List[Tuple[int, bool, bool]]]:
    """
    Returns: (is_initial_record, list of changes)
    - is_initial_record: True if old was empty and new has data
    - changes: list of (student_index, was_present, is_now_present)
    """
    old_bitstr = old_bitstr.strip() if old_bitstr else ""
    new_bitstr = new_bitstr.strip() if new_bitstr else ""

    # Check if this is an initial record
    is_initial_record = not bool(old_bitstr) and bool(new_bitstr)
    
    # If initial record, we need to process ALL students
    if is_initial_record:
        changes = []
        for i in range(len(new_bitstr)):
            is_now_present = new_bitstr[i] == "1"
            changes.append((i, False, is_now_present))  # was_present is always False for initial
        return True, changes
    
    # If update with no changes, return empty
    if old_bitstr == new_bitstr:
        return False, []
    
    # Regular update - find only changed students
    max_len = max(len(old_bitstr), len(new_bitstr))
    changes = []

    for i in range(max_len):
        old_bit = old_bitstr[i] if i < len(old_bitstr) else "0"
        new_bit = new_bitstr[i] if i < len(new_bitstr) else "0"

        was_present = old_bit == "1"
        is_now_present = new_bit == "1"

        if was_present != is_now_present:
            changes.append((i, was_present, is_now_present))

    return False, changes


#############################################
# 🧩 OPTIMIZED Updater: Student Attendance Summary
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
        # Update existing summary - ONLY if there are actual changes
        new_total = summary.total_classes + total_classes_delta
        new_attended = max(0, summary.attended + attended_delta)
        new_percentage = round((new_attended / new_total * 100) if new_total > 0 else 0.0, 2)

        # Only update if something actually changed
        if (new_total != summary.total_classes or 
            new_attended != summary.attended or 
            new_percentage != summary.percentage):
            
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
        else:
            logger.debug(f"🔍 No changes needed for student {student.id}, subject {subject.id}")


#############################################
# 🧩 OPTIMIZED Updater: Teacher Subject Summary
#############################################

async def update_teacher_subject_summary(
    attendance: Attendance,
    teacher: Link,
    subject: Link,
    is_initial_record: bool,
    old_percentage: Optional[float] = None,
    new_percentage: Optional[float] = None
):
    """
    SMART: Handles both initial records and updates efficiently
    """
    try:
        logger.info(f"🛠️ Starting SMART update_teacher_subject_summary()")
        logger.info(f"👉 Attendance ID: {attendance.id}")
        logger.info(f"👉 Is initial record: {is_initial_record}")
        logger.info(f"👉 Old percentage: {old_percentage}")
        logger.info(f"👉 New percentage: {new_percentage}")

        # Find existing summary
        summary = await TeacherSubjectSummary.find_one(
            TeacherSubjectSummary.teacher == DBRef("teachers", teacher.id),
            TeacherSubjectSummary.subject == DBRef("subjects", subject.id)
        )

        if is_initial_record:
            # For initial records, we MUST create/update regardless
            logger.info("🎯 Initial record - processing full update")
            
            if not summary:
                logger.info("⚡ No existing summary found → Creating new one")
                new_total_sessions = 1
                new_avg_attendance = Decimal(str(new_percentage))

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
                logger.info("🔄 Initial record with existing summary → Updating")
                old_total = summary.total_sessions_conducted
                old_avg = summary.average_attendance_percentage
                
                new_avg_attendance = ((old_avg * old_total) + Decimal(str(new_percentage))) / (old_total + 1)
                new_total_sessions = old_total + 1

                defaulter_count, at_risk_count, top_performer_count = await get_attendance_category_counts(subject.id)

                await summary.set({
                    TeacherSubjectSummary.total_sessions_conducted: new_total_sessions,
                    TeacherSubjectSummary.average_attendance_percentage: PyDecimal(str(round(new_avg_attendance, 2))),
                    TeacherSubjectSummary.defaulter_count: defaulter_count,
                    TeacherSubjectSummary.at_risk_count: at_risk_count,
                    TeacherSubjectSummary.top_performer_count: top_performer_count
                })
                logger.info(f"✅ Updated TeacherSubjectSummary for teacher {teacher.id}, subject {subject.id}")

        else:
            # For updates, only proceed if percentage changed
            if old_percentage == new_percentage:
                logger.info(f"🔍 No percentage change detected ({old_percentage} → {new_percentage}), skipping update")
                return

            if not summary:
                logger.warning(f"⚠️ No existing summary found for update, creating new one")
                new_total_sessions = 1  # This shouldn't happen, but handle it
                new_avg_attendance = Decimal(str(new_percentage))

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
                logger.info("📝 Existing summary found → Updating with changed percentage")
                old_total = summary.total_sessions_conducted
                old_avg = summary.average_attendance_percentage

                # Adjust average: remove old percentage, add new percentage
                new_avg_attendance = ((old_avg * old_total) - Decimal(str(old_percentage)) + Decimal(str(new_percentage))) / old_total

                defaulter_count, at_risk_count, top_performer_count = await get_attendance_category_counts(subject.id)

                await summary.set({
                    TeacherSubjectSummary.total_sessions_conducted: old_total,  # unchanged for updates
                    TeacherSubjectSummary.average_attendance_percentage: PyDecimal(str(round(new_avg_attendance, 2))),
                    TeacherSubjectSummary.defaulter_count: defaulter_count,
                    TeacherSubjectSummary.at_risk_count: at_risk_count,
                    TeacherSubjectSummary.top_performer_count: top_performer_count
                })
                logger.info(f"✅ Updated TeacherSubjectSummary for teacher {teacher.id}, subject {subject.id}")

        logger.info("✅ update_teacher_subject_summary() completed successfully")

    except Exception as e:
        logger.error(f"🚨 Error in update_teacher_subject_summary for attendance {attendance.id}: {e}")


#############################################
# 🧩 OPTIMIZED Updater: Subject Session Stats
#############################################

async def update_subject_session_stats(
    attendance: Attendance,
    teacher: Link,
    subject: Link,
    is_initial_record: bool,
    present_count: int = None,
    absent_count: int = None,
    percentage: float = None
):
    """
    SMART: Always creates/updates session stats, but only if values changed
    """
    logger.info(f"🛠️ Starting SMART update_subject_session_stats()")

    session = await SubjectSessionStats.find_one(
        SubjectSessionStats.session_id == DBRef("attendances", attendance.id),
        SubjectSessionStats.subject == DBRef("subjects", subject.id)
    )

    if session:
        # Check if we actually need to update
        if (session.present_count == present_count and 
            session.absent_count == absent_count and 
            session.percentage_present == percentage):
            logger.info("🔍 No changes in session stats, skipping update")
            return

        logger.info("🔄 Updating existing SubjectSessionStats record")
        await session.set({
            SubjectSessionStats.present_count: present_count,
            SubjectSessionStats.absent_count: absent_count,
            SubjectSessionStats.percentage_present: percentage,
        })
        logger.info(f"✅ Updated SubjectSessionStats for session_id: {attendance.id}")
    else:
        # Always create if it doesn't exist (for both initial and updates)
        logger.info("✨ Creating new SubjectSessionStats record")
        new_session = SubjectSessionStats(
            session_id=DBRef("attendances", attendance.id),
            subject=subject,
            date=date.today(),
            component_type=getattr(attendance, "component_type", "Lecture"),
            present_count=present_count,
            absent_count=absent_count,
            percentage_present=percentage,
        )
        await new_session.insert()
        logger.info(f"✅ Created new SubjectSessionStats for session_id: {attendance.id}")

    logger.info("✅ update_subject_session_stats() completed successfully")


#############################################
# ✅ SMART: Handle Student Attendance with Smart Detection
#############################################

async def handle_attendance_update(attendance: Attendance, old_bitstr: str, new_bitstr: str):
    old_bitstr = old_bitstr.strip() if old_bitstr else ""
    new_bitstr = new_bitstr.strip() if new_bitstr else ""

    if old_bitstr == new_bitstr:
        logger.info(f"✅ No change in attendance bits for {attendance.id}")
        return

    # SMART: Detect if this is initial record or update with changes
    is_initial_record, changed_students = calculate_bit_changes(old_bitstr, new_bitstr)
    
    logger.info(f"📊 Processing attendance update: {attendance.id}")
    logger.info(f"   Type: {'INITIAL RECORD' if is_initial_record else 'UPDATE WITH CHANGES'}")
    logger.info(f"   Old: {old_bitstr}")
    logger.info(f"   New: {new_bitstr}")
    logger.info(f"   Changed students: {len(changed_students)}")

    # Calculate percentages for teacher/subject summaries
    old_present_count = old_bitstr.count("1") if old_bitstr else 0
    new_present_count = new_bitstr.count("1")
    total_students = len(new_bitstr) if new_bitstr else len(old_bitstr)
    
    old_percentage = (old_present_count / total_students * 100) if total_students > 0 else 0.0
    new_percentage = (new_present_count / total_students * 100) if total_students > 0 else 0.0

    logger.info(f"📊 Percentage: {old_percentage:.2f}% → {new_percentage:.2f}%")

    # Fetch all links inside Attendance
    try:
        await attendance.fetch_all_links()
    except Exception as e:
        logger.error(f"🚨 Error fetching links for attendance {attendance.id}: {e}")
        return

    # Resolve session context
    session_context = await resolve_session_context(attendance)
    if not session_context:
        logger.error(f"🚨 Failed to resolve session context for attendance {attendance.id}")
        return

    subject, program, department, semester, teacher = session_context

    # Fetch students
    student_list = await fetch_students(program, semester, department)
    if not student_list:
        logger.warning(f"⚠️ No students found")
        return

    # ✅ SMART STEP 1: Update Student Attendance Summary
    if is_initial_record:
        logger.info("🎯 Processing ALL students for initial record")
        # Process all students for initial record
        for index, (_, was_present, is_now_present) in enumerate(changed_students):
            if index >= len(student_list):
                continue
            student = student_list[index]
            await update_student_attendance_summary(
                attendance, student, subject, was_present, is_now_present, is_initial_record
            )
    else:
        logger.info("🎯 Processing ONLY CHANGED students for update")
        # Process only changed students for updates
        for index, was_present, is_now_present in changed_students:
            if index >= len(student_list):
                continue
            student = student_list[index]
            await update_student_attendance_summary(
                attendance, student, subject, was_present, is_now_present, is_initial_record
            )

    # ✅ SMART STEP 2: Update Teacher Subject Summary
    try:
        await update_teacher_subject_summary(
            attendance, teacher, subject, is_initial_record, old_percentage, new_percentage
        )
    except Exception as e:
        logger.error(f"🚨 Error updating TeacherSubjectSummary for attendance {attendance.id}: {e}")

    # ✅ SMART STEP 3: Update Subject Session Stats
    try:
        await update_subject_session_stats(
            attendance, teacher, subject, is_initial_record, 
            new_present_count, total_students - new_present_count, new_percentage
        )
    except Exception as e:
        logger.error(f"🚨 Error updating SubjectSessionStats for attendance {attendance.id}: {e}")

    logger.info(f"✅ Completed processing for Attendance {attendance.id}")


async def resolve_session_context(attendance: Attendance) -> Optional[tuple]:
    """Resolve session context from attendance"""
    try:
        session = None
        if attendance.session:
            session = attendance.session
            if isinstance(session, Link):
                session = await session.fetch_link()
            await session.fetch_all_links()
        elif attendance.exception_session:
            exception_session = attendance.exception_session
            if isinstance(exception_session, Link):
                exception_session = await exception_session.fetch_link()
            session = exception_session.session
            if isinstance(session, Link):
                session = await session.fetch_link()
            await session.fetch_all_links()

        if not session:
            return None

        subject = session.subject
        program = session.program
        department = session.department
        semester = int(session.semester)
        teacher = session.teacher

        return subject, program, department, semester, teacher
    except Exception as e:
        logger.error(f"🚨 Error resolving session context: {e}")
        return None


async def fetch_students(program, semester, department) -> List[Student]:
    """Fetch students for the given context"""
    try:
        return await Student.find_many(
            Student.program == program,
            Student.semester == semester,
            Student.department == department
        ).sort("roll_no").to_list()
    except Exception as e:
        logger.error(f"🚨 Error fetching students: {e}")
        return []


async def get_attendance_category_counts(subject_id: ObjectId) -> tuple[int, int, int]:
    """Calculate attendance category counts"""
    try:
        summaries = await StudentAttendanceSummary.find(
            StudentAttendanceSummary.subject == DBRef("subjects", subject_id)
        ).to_list()

        defaulter = at_risk = top_performer = 0

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
# 👂 Change Stream Watcher (unchanged)
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
                    attendance = await Attendance.get(doc_id, fetch_links=True)
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