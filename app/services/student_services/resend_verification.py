from fastapi import Request
from fastapi.responses import JSONResponse
from app.utils.send_otp import generate_and_store_otp
from app.models.allModel import OtpRequest
from app.schemas.student import Student
from app.utils.publisher import send_to_queue

async def resend_verification_otp(request_data: OtpRequest):
    try:
        email = request_data.email
        
        # 1. Check if student exists
        student = await Student.find_one(Student.email == email)
        if not student:
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "message": "Student not found"
                }
            )

        # 2. Check if already verified
        if student.is_verified:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "message": "Email already verified"
                }
            )

        # 3. Generate and Store OTP
        try:
            otp = await generate_and_store_otp(email)
        except ValueError as e:
            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "message": str(e)
                }
            )

        # 4. Send Email
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <p>Hello <b>{student.first_name}</b>,</p>

            <p>Here is your new email verification OTP:</p>

            <h2 style="letter-spacing: 4px;">{otp}</h2>

            <p>This OTP will expire in <b>10 minutes</b>.</p>

            <p>If you didn't request this, please ignore.</p>

            <br />
            <p>Regards,<br />MarkMe Team</p>
        </body>
        </html>
        """

        await send_to_queue(
            "email_queue",
            {
                "type": "send_email",
                "data": {
                    "to": email,
                    "subject": "Resend: Verify your email - MarkMe",
                    "body": html_body,
                    "is_html": True   
                }
            },
            priority=5
        )

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Verification OTP resent successfully"
            }
        )

    except Exception as e:
        print(f"[resend_verification_otp] Error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"Server error: {str(e)}"
            }
        )
