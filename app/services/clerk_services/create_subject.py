from fastapi import HTTPException
from app.core.database import get_db
from app.schemas.subject import Subject
from pydantic import ValidationError
from bson.objectid import ObjectId
from app.core.redis import redis_client

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
        # Check if subject with same code AND component exists
        existing_subject = await Subject.find_one({
            "subject_code": request.subject_code,
            "component": request.component
        })

        print(f"Existing Subject: {existing_subject}")
        
        if existing_subject:
            raise HTTPException(
                status_code=400,
                detail={
                    "status": "fail",
                    "message": f"Subject with code {request.subject_code} and component {request.component} already exists"
                }
            )

        # Create Subject Beanie model
        subject_data = Subject(
            subject_code=request.subject_code,
            subject_name=request.subject_name,
            department=request.department,
            semester=request.semester,
            program=request.program,
            credit=request.credit,
            component=request.component,  
        )

        # Save subject to database
        await subject_data.save()

        # Delete cache for subjects to ensure fresh data
        cache_key_subject = f"subject:{user_data["program"]}"
        await redis_client.delete(cache_key_subject)

        return {
            "status": "success",
            "message": "Subject created successfully",
            "data": {
                "subject_code": subject_data.subject_code,
                "subject_name": subject_data.subject_name,
                "department": subject_data.department,
                "semester": subject_data.semester,
                "program": subject_data.program,
                "credit": subject_data.credit,
                "component": subject_data.component
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
        raise he

    except Exception as e:
        print(f"Subject Creation error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={
                "status": "fail",
                "message": f"Error creating subject: {str(e)}"
            }
        )