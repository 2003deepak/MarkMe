from fastapi import Request
from fastapi.responses import JSONResponse
from app.schemas.teacher import Teacher
from app.schemas.subject import Subject
from app.models.allModel import TeacherUpdateRequest
from app.core.redis import redis_client
from beanie.operators import In
import logging

logger = logging.getLogger("app.services.clerk_services.update_teacher")


async def update_teacher_data(request: Request, request_model: TeacherUpdateRequest):
    """
    PATCH /teacher - Update teacher data and ensure subject links remain as DBRefs.
    """

    logger.info("FLOW START: update_teacher_data | intent=update_teacher_and_sync_subject_links | "
                "note=Ensure teacher->subject DBRef referencing remains consistent.")

    # 1️⃣ Auth check
    user_role = request.state.user.get("role")
    if user_role != "clerk":
        return JSONResponse(status_code=403, content={"error": "Unauthorized access"})
    logger.info(f"STEP: auth_check | user_role={user_role}")

    # 2️⃣ Find teacher
    lookup_field = "email" if request_model.email else "teacher_id"
    value = request_model.email or request_model.teacher_id
    teacher_doc = await Teacher.find_one({lookup_field: value})
    if not teacher_doc:
        return JSONResponse(status_code=404, content={"error": "Teacher not found"})

    logger.info(
        f"STEP: find_teacher | lookup_field={lookup_field} | value={value}\n"
        f"STEP: teacher_loaded | teacher_id={teacher_doc.teacher_id} | email={teacher_doc.email} | "
        f"department={teacher_doc.department}"
    )

    # 3️⃣ Fetch current subject links
    await teacher_doc.fetch_link(Teacher.subjects_assigned)
    old_subject_codes = {s.subject_code for s in teacher_doc.subjects_assigned} if teacher_doc.subjects_assigned else set()
    logger.info(f"STEP: fetch_linked_subjects | current_subjects={list(old_subject_codes)}")

    # 4️⃣ Validate new subjects
    if request_model.subjects_assigned:
        new_subject_codes = set(request_model.subjects_assigned)
        logger.info(f"STEP: validate_new_subjects | action=query_subjects_by_codes | codes={list(new_subject_codes)}")

        # Fetch ALL subjects matching these codes (Lecture + Lab)
        new_subject_docs = await Subject.find(
            In(Subject.subject_code, list(new_subject_codes))
        ).to_list()

        if not new_subject_docs:
            return JSONResponse(status_code=404, content={"error": "No valid subjects found."})

        found_codes = [subj.subject_code for subj in new_subject_docs]
        logger.info(f"STEP: new_subjects_validated | found_count={len(found_codes)} | found_codes={found_codes}")
    else:
        new_subject_codes, new_subject_docs = set(), []

    # 5️⃣ Update teacher fields
    update_data = request_model.model_dump(exclude_unset=True)

    if "department" in update_data and request_model.department:
        teacher_doc.department = request_model.department

    if "subjects_assigned" in update_data and new_subject_docs:
        teacher_doc.subjects_assigned = new_subject_docs  # ✅ no deduplication

    logger.info("STEP: update_teacher_fields | applying changes to teacher_doc (if present)")
    await teacher_doc.save()
    logger.info(f"STEP: save_teacher | action=teacher_doc.save() | teacher_id={teacher_doc.teacher_id}")

    # 6️⃣ Add teacher DBRef to each of those subjects
    to_add = new_subject_codes - old_subject_codes
    if to_add:
        logger.info(f"STEP: add_new_assignments | count={len(to_add)} | codes={list(to_add)}")

        subjects_to_add = await Subject.find(In(Subject.subject_code, list(to_add))).to_list()
        for subj in subjects_to_add:
            subj.teacher_assigned = teacher_doc
            await subj.save()
            logger.debug(f"Linked teacher {teacher_doc.teacher_id} to subject {subj.subject_code} (DBRef)")

        logger.info(f"Linked teacher {teacher_doc.teacher_id} to {len(subjects_to_add)} new subjects as DBRef.")

    logger.info(f"FLOW COMPLETE: update_teacher_data | status=success | teacher_id={teacher_doc.teacher_id}")

    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "teacher_id": teacher_doc.teacher_id,
            "email": teacher_doc.email,
            "subjects_assigned_count": len(teacher_doc.subjects_assigned),
        },
    )
