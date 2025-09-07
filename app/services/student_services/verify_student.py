from fastapi import HTTPException
from jose import JWTError
from app.utils.token_utils import decode_verification_token
from app.schemas.student import Student


async def verify_student_email(token: str):
    """
    Verifies a student's email using the provided JWT token.
    """
    try:
        # ✅ Decode token to extract email
        email = decode_verification_token(token)

        # ✅ Find student in DB
        student = await Student.find_one(Student.email == email)
        if not student:
            raise HTTPException(
                status_code=404,
                detail={"status": "fail", "message": "Student not found"}
            )

        # ✅ Already verified?
        if student.is_verified:
            return {
                "status": "success",
                "message": "Email already verified"
            }

        # ✅ Update to verified
        student.is_verified = True
        await student.save()

        return {
            "status": "success",
            "message": "Email verified successfully"
        }

    except JWTError:
        raise HTTPException(
            status_code=400,
            detail={"status": "fail", "message": "Invalid or expired token"}
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"status": "fail", "message": f"Error verifying email: {str(e)}"}
        )
