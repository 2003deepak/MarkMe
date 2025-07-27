# from motor.motor_asyncio import AsyncIOMotorClient
# from app.models.attendance import Attendance
# from app.models.derived.student_session_attendance import StudentSessionAttendance
# from app.models.derived.class_session_summary import ClassSessionSummary
# from app.models.derived.subject_session_summary import SubjectSessionSummary
# from app.models.derived.department_session_summary import DepartmentSessionSummary
# from app.database import db  # your init_beanie also sets db.client
# from beanie.operators import Set
# from bson import ObjectId
# import asyncio


# async def watch_attendance_changes():
#     # Access underlying Motor client from Beanie
#     client: AsyncIOMotorClient = db.client
#     collection = client[db.name]["attendance"]

#     # Only listen for updates, not inserts
#     pipeline = [{"$match": {"operationType": "update"}}]

#     async with collection.watch(pipeline) as stream:
#         async for change in stream:
#             doc_id = change["documentKey"]["_id"]
#             updated_fields = change["updateDescription"]["updatedFields"]

#             # Only react if meaningful update
#             if not {"bit_mask", "student_ids"} & set(updated_fields):
#                 continue

#             # Load the document using Beanie
#             attendance = await Attendance.get(doc_id)
#             if not attendance:
#                 continue

#             if not attendance.student_ids or attendance.bit_mask == 0:
#                 continue

#             await handle_attendance_update(attendance)


# async def handle_attendance_update(att: Attendance):
#     bitmask = att.bit_mask
#     student_ids = att.student_ids

#     total = len(student_ids)
#     present = 0

#     for i, student_id in enumerate(student_ids):
#         is_present = (bitmask >> i) & 1
#         present += is_present

#         # Upsert StudentSessionAttendance
#         existing = await StudentSessionAttendance.find_one(
#             StudentSessionAttendance.attendance_id == att.id,
#             StudentSessionAttendance.student_id == student_id,
#         )

#         if existing:
#             await existing.set(Set({ "status": bool(is_present) }))
#         else:
#             await StudentSessionAttendance(
#                 attendance_id=att.id,
#                 student_id=student_id,
#                 subject_id=att.subject_id,
#                 timetable_id=att.timetable_id,
#                 status=bool(is_present),
#                 date=att.date,
#             ).insert()

#     absent = total - present

#     # Upsert ClassSessionSummary
#     await upsert_summary(
#         ClassSessionSummary,
#         {"attendance_id": att.id},
#         {
#             "attendance_id": att.id,
#             "timetable_id": att.timetable_id,
#             "total_students": total,
#             "present": present,
#             "absent": absent,
#             "date": att.date,
#         }
#     )

#     # Upsert SubjectSessionSummary
#     await upsert_summary(
#         SubjectSessionSummary,
#         {"attendance_id": att.id},
#         {
#             "attendance_id": att.id,
#             "subject_id": att.subject_id,
#             "total_students": total,
#             "present": present,
#             "absent": absent,
#             "date": att.date,
#         }
#     )

#     # Upsert DepartmentSessionSummary
#     await upsert_summary(
#         DepartmentSessionSummary,
#         {"attendance_id": att.id},
#         {
#             "attendance_id": att.id,
#             "department": att.department,
#             "program": att.program,
#             "semester": att.semester,
#             "total_students": total,
#             "present": present,
#             "absent": absent,
#             "date": att.date,
#         }
#     )

#     print(f"✅ Processed derived updates for attendance: {att.id}")


# async def upsert_summary(model, query: dict, data: dict):
#     existing = await model.find_one(model.attendance_id == query["attendance_id"])
#     if existing:
#         await existing.set(Set({
#             "present": data["present"],
#             "absent": data["absent"]
#         }))
#     else:
#         await model(**data).insert()
