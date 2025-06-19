from fastapi import HTTPException
from app.core.database import get_db
from app.schemas.subject import Subject, SubjectRepository
from pydantic import ValidationError

async def create_subject(request,user_data):

    if user_data["role"] != "clerk" :
        raise HTTPException(
                status_code=400,
                detail={
                    "status": "fail",
                    "message": "You Dont have right to create clerk"
                }
            )


    try:
        # Get database connection
        db = get_db()
        repo = SubjectRepository(db.client, db.name)

        # Validate request using Subject model
        subject_data = Subject(
            subject_code=request.subject_code,
            subject_name=request.subject_name,
            department=request.department,
            semester=request.semester,
            program=request.program,
            type=request.type,
            credit=request.credit,
            teacher_assigned=[]
        )

        # Check if subject exists
        if await db.subjects.find_one({"subject_code": subject_data.subject_code.upper()}):
            raise HTTPException(
                status_code=400,
                detail={
                    "status": "fail",
                    "message": "Subject already exists"
                }
            )

        # Convert Subject to dict and apply timestamps
        subject_dict = subject_data.dict()  # Fixed: Use subject_data instead of subject_dict
        subject_dict = await repo._apply_timestamps(subject_dict)  # Pass dict to _apply_timestamps

        # Insert subject into database
        result = await db.subjects.insert_one(subject_dict)

        return {
            "status": "success",
            "message": "Subject created successfully",
            "data": {
                "subject_code": subject_dict["subject_code"],
                "subject_name": subject_dict["subject_name"],
                "department": subject_dict["department"],
                "semester": subject_dict["semester"],
                "program": subject_dict["program"],
                "type": subject_dict["type"],
                "credit_hours": subject_dict["credit"]
            }
        }

    except ValidationError as e:
        # Extract the first error message
        error_msg = str(e.errors()[0]['msg'])
        raise HTTPException(
            status_code=422,
            detail={
                "status": "fail",
                "message": error_msg
            }
        )
    except HTTPException as he:
        # If it's already in our format, just re-raise
        if isinstance(he.detail, dict) and "status" in he.detail and "message" in he.detail:
            raise he
        # Otherwise, reformat it
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