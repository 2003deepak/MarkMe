from fastapi import HTTPException
from app.core.database import get_db
from app.schemas.subject import Subject, SubjectRepository, Component
from pydantic import ValidationError
from bson.objectid import ObjectId


async def create_subject(request, user_data):
    if user_data["role"] != "clerk":
        raise HTTPException(
            status_code=400,
            detail={
                "status": "fail",
                "message": "You don't have the right to create a subject"
            }
        )

    try:
        db = get_db()
        repo = SubjectRepository(db.client, db.name)
        await repo._ensure_indexes()

        # Build Component list from request
        components = [Component(type=comp.type) for comp in request.components]

        subject_data = Subject(
            subject_code=request.subject_code,
            subject_name=request.subject_name,
            department=request.department,
            semester=request.semester,
            program=request.program,
            credit=request.credit,
            components=components
        )

        existing = await db.subjects.find_one({"subject_code": subject_data.subject_code.upper()})
        if existing:
            raise HTTPException(
                status_code=400,
                detail={
                    "status": "fail",
                    "message": "Subject with this code already exists"
                }
            )

        subject_dict = subject_data.dict()
        subject_dict = await repo._apply_timestamps(subject_dict)

        await db.subjects.insert_one(subject_dict)

        return {
            "status": "success",
            "message": "Subject created successfully",
            "data": {
                "subject_code": subject_dict["subject_code"],
                "subject_name": subject_dict["subject_name"],
                "department": subject_dict["department"],
                "semester": subject_dict["semester"],
                "program": subject_dict["program"],
                "credit": subject_dict["credit"],
                "components": subject_dict["components"]
            }
        }

    except ValidationError as e:
        error_msg = str(e.errors()[0]['msg'])
        raise HTTPException(
            status_code=422,
            detail={
                "status": "fail",
                "message": error_msg
            }
        )

    except HTTPException as he:
        if isinstance(he.detail, dict) and "status" in he.detail and "message" in he.detail:
            raise he
        raise HTTPException(
            status_code=he.status_code,
            detail={
                "status": "fail",
                "message": he.detail
            }
        )

    except Exception as e:
        print(f"Subject Creation error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={
                "status": "fail",
                "message": f"Error creating subject: {str(e)}"
            }
        )
