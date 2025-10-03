from fastapi import HTTPException
from fastapi.responses import JSONResponse
from app.core.database import get_db
from app.schemas.subject import Subject
from pydantic import ValidationError
from bson.objectid import ObjectId
from app.core.redis import redis_client

async def create_subject(request, request_model):
    if request.state.user.get("role") != "clerk":
        return JSONResponse(
            status_code=400,
            content={
                "status": "fail",
                "message": "Only Clerk can create new subjects"
            }
        )

    try:
        # Check if subject with same code AND component exists
        existing_subject = await Subject.find_one({
            "subject_code": request_model.subject_code,
            "component": request_model.component
        })

        print(f"Existing Subject: {existing_subject}")
        
        if existing_subject:
        
            return JSONResponse(
                status_code=400,
                content={
                    "status": "fail",
                    "message": f"Subject with code {request_model.subject_code} and component {request_model.component} already exists"
                }
            )

        # Create Subject Beanie model
        subject_data = Subject(
            subject_code=request_model.subject_code,
            subject_name=request_model.subject_name,
            department=request_model.department,
            semester=request_model.semester,
            program=request_model.program,
            credit=request_model.credit,
            component=request_model.component,  
        )

        # Save subject to database
        await subject_data.save()

        # Delete cache for subjects to ensure fresh data
        cache_key_subject = [
            f"subjects:{request.state.user.get('program')}:{request.state.user.get('department')}:{request.state.user.get('semester')}",
            f"subject:{request.state.user.get('program')}"
        ]


        await redis_client.delete(*cache_key_subject)

        return JSONResponse(
            status_code=200,  
            content={
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
        )

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