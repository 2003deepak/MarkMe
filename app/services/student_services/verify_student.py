from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from jose import JWTError
from app.utils.token_utils import decode_verification_token
from app.schemas.student import Student
from pydantic import BaseModel

class VerifyEmailRequest(BaseModel):
    token: str

async def verify_student_email(request: Request):
    
    try:
        
         # Get token from query parameter 
        token = request.query_params.get("token")
        
        if not token:
            return JSONResponse(
                status_code=400,
                content={
                    "status": "fail", 
                    "message": "Token is required as query parameter"
                }
            )
        
        # ✅ Decode token to extract email
        email = decode_verification_token(token)

        # ✅ Find student in DB
        student = await Student.find_one(Student.email == email)
        if not student:
            return JSONResponse(
                status_code=404,
                content={
                    "status": "fail", 
                    "message": "Student not found"
                }
            )

        # ✅ Already verified?
        if student.is_verified:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "message": "Email already verified"
                }
            )

        # ✅ Update to verified
        student.is_verified = True
        await student.save()

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "Email verified successfully"
            }
        )

    except JWTError:
        return JSONResponse(
            status_code=400,
            content={
                "status": "fail", 
                "message": "Invalid or expired token"
            }
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "status": "fail", 
                "message": f"Error verifying email: {str(e)}"
            }
        )