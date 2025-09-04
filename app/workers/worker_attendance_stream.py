import asyncio
import logging
from typing import Optional
from beanie import PydanticObjectId, Link, Document
from beanie.operators import Set, AddToSet, Pull
from app.core.database import init_db
from bson import ObjectId, DBRef
from app.schemas.attendance import Attendance
from app.schemas.student_attendance_summary import StudentAttendanceSummary
from app.schemas.student import Student

# Logger
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


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

    # Determine context: session, subject, program, etc.
    session = None
    subject = None
    program = department = semester = academic_year = None

    is_initial_record = not bool(old_bitstr) and bool(new_bitstr)
    logger.info(f"   Is initial record? {is_initial_record}")

    # Fetch all links
    try:
        await attendance.fetch_all_links()
    except Exception as e:
        logger.error(f"🚨 Error fetching links for attendance {attendance.id}: {e}")
        return

    if attendance.session:
        try:
            await attendance.session.fetch_all_links()
            session = attendance.session
        except Exception as e:
            logger.error(f"🚨 Error fetching session links for attendance {attendance.id}: {e}")
            return
    elif attendance.exception_session:
        try:
            await attendance.exception_session.fetch_all_links()
            await attendance.exception_session.session.fetch_all_links()
            session = attendance.exception_session.session
        except Exception as e:
            logger.error(f"🚨 Error fetching exception session links for attendance {attendance.id}: {e}")
            return
    else:
        logger.warning(f"⚠️ No session or exception_session in attendance {attendance.id}")
        return

    if session:
        try:
            await session.fetch_all_links()
            subject = session.subject
            program = session.program
            department = session.department
            semester = session.semester
            academic_year = session.academic_year
        except Exception as e:
            logger.error(f"🚨 Error fetching session details for session {session.id}: {e}")
            return

    if not all([program, semester, department, subject]):
        logger.warning(f"⚠️ Missing required context for attendance {attendance.id}")
        return

    try:
        semester = int(semester)
    except (ValueError, TypeError):
        logger.error(f"⚠️ Invalid semester value: {semester}")
        return

    # Fetch all students in roll order
    try:
        student_list = await Student.find_many(
            Student.program == program,
            Student.semester == semester,
            Student.department == department
        ).sort("roll_no").to_list()
    except Exception as e:
        logger.error(f"🚨 Error fetching students for program: {program}, department: {department}, semester: {semester}: {e}")
        return

    if not student_list:
        logger.warning(f"⚠️ No students found for program: {program}, department: {department}, semester: {semester}")
        return

    if len(student_list) != len(new_bitstr):
        logger.warning(
            f"⚠️ Student count mismatch: {len(student_list)} students vs {len(new_bitstr)} bits"
        )
        return

    # Determine which student indices changed
    changed_indices = [
        i for i in range(min(len(old_bitstr), len(new_bitstr)))
        if old_bitstr[i] != new_bitstr[i]
    ]
    changed_indices += list(range(len(old_bitstr), len(new_bitstr)))

    logger.info(f"🔄 Updating attendance for indices: {changed_indices}")

    for i in changed_indices:
        if i >= len(student_list):
            logger.warning(f"⚠️ Index {i} out of range for student list (length: {len(student_list)})")
            continue

        student = student_list[i]
        # Verify student is a valid Student document
        if not isinstance(student, Student):
            logger.error(f"⚠️ Invalid student at index {i}: {student}")
            continue

        new_present = i < len(new_bitstr) and new_bitstr[i] == "1"
        old_present = i < len(old_bitstr) and old_bitstr[i] == "1"

        # Verify subject is a valid Subject document or Link
        if not isinstance(subject, (Link, Document)):
            logger.error(f"⚠️ Invalid subject: {subject}")
            continue

        # Get existing summary
        try:
            summary = await StudentAttendanceSummary.find_one(
                StudentAttendanceSummary.student == DBRef("students", student.id),
                StudentAttendanceSummary.subject == DBRef("subjects", subject.id)
            )
            logger.debug(f"🔍 Queried summary for student {student.id}, subject {subject.id}: {'Found' if summary else 'Not found'}")
        except Exception as e:
            logger.error(f"🚨 Error querying StudentAttendanceSummary for student {student.id}, subject {subject.id}: {e}")
            continue

        # Calculate deltas
        total_classes_delta = 1 if is_initial_record else 0
        attended_delta = 0

        if is_initial_record:
            attended_delta = 1 if new_present else 0
        else:
            if old_present and not new_present:
                attended_delta = -1
            elif not old_present and new_present:
                attended_delta = 1

        if not summary:
            # Create new summary
            total_classes = 1 if is_initial_record else 0
            attended = 1 if (is_initial_record and new_present) else 0
            percentage = round((attended / total_classes * 100) if total_classes > 0 else 0.0, 2)

            summary = StudentAttendanceSummary(
                student=student,
                subject=subject,
                total_classes=total_classes,
                attended=attended,
                percentage=percentage,
                sessions_present=[attendance.id] if new_present else [],
                created_at=attendance.created_at or None,
                updated_at=attendance.updated_at or None
            )
            try:
                await summary.insert()
                logger.info(f"📝 Created summary for student {student.id}, subject {subject.id}")
            except Exception as e:
                logger.error(f"🚨 Error inserting StudentAttendanceSummary for student {student.id}, subject {subject.id}: {e}")
                continue
        else:
            # Update existing summary
            new_total = summary.total_classes + total_classes_delta
            new_attended = max(0, summary.attended + attended_delta)  # Ensure attended doesn't go negative
            new_percentage = round((new_attended / new_total * 100) if new_total > 0 else 0.0, 2)

            update_ops = [
                Set({
                    StudentAttendanceSummary.total_classes: new_total,
                    StudentAttendanceSummary.attended: new_attended,
                    StudentAttendanceSummary.percentage: new_percentage,
                    StudentAttendanceSummary.updated_at: attendance.updated_at or None,
                })
            ]

            # Always use the same DBRef format
            print(DBRef("attendances",'68b34724a2727bcf07305825'))
                   
            try:
                await summary.update(*update_ops)
                logger.info(f"✅ Updated summary for student {student.id}, subject {subject.id}")
            except Exception as e:
                logger.error(f"🚨 Error updating StudentAttendanceSummary for student {student.id}, subject {subject.id}: {e}")
                continue

    logger.info(f"✅ Processed {len(changed_indices)} student(s) for Attendance {attendance.id}")


async def watch_attendance_changes():
    logger.info("🚀 Initializing DB connection...")
    try:
        await init_db()
        logger.info("✅ Database connected.")
    except Exception as e:
        logger.error(f"🚨 Failed to initialize database: {e}")
        raise

    # Watch for updates with pre-image
    pipeline = [{"$match": {"operationType": "update"}}]
    collection = Attendance.get_motor_collection()

    logger.info("👂 Listening for updates on Attendance collection...")

    try:
        async with collection.watch(
            pipeline,
            full_document="updateLookup",           # Fetch full updated document
            full_document_before_change="required"  # Require pre-image
        ) as stream:
            async for change in stream:
                doc_id = change["documentKey"]["_id"]
                logger.info(f"🔔 Update detected: {doc_id}")

                new_doc = change.get("fullDocument")
                old_doc = change.get("fullDocumentBeforeChange")

                if not new_doc or not old_doc:
                    logger.warning(f"⚠️ Missing full document or pre-image for {doc_id}")
                    continue

                new_bitstr = new_doc.get("students", "")
                old_bitstr = old_doc.get("students", "")

                try:
                    attendance = await Attendance.get(doc_id)
                    if not attendance:
                        logger.error(f"❌ Attendance {doc_id} not found after lookup.")
                        continue

                    await handle_attendance_update(attendance, old_bitstr, new_bitstr)
                except Exception as e:
                    logger.error(f"🚨 Error processing attendance update for {doc_id}: {e}")
                    continue

    except Exception as e:
        logger.error(f"🚨 Watch stream error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(watch_attendance_changes())