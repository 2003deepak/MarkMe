from fastapi import Request
from app.schemas.student import Student
from app.utils.send_otp import verify_otp
from app.models.allModel import OtpRequest
from fastapi.responses import JSONResponse


# ─────────────────────────────
# HTML FALLBACK (Desktop users)
# ─────────────────────────────

SUCCESS_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Email Verified</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            background-color: #f4f6f8;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
        }}
        .card {{
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 4px 10px rgba(0,0,0,0.1);
            text-align: center;
        }}
        h1 {{
            color: #2e7d32;
        }}
        p {{
            color: #555;
        }}
    </style>
</head>
<body>
    <div class="card">
        <h1>✅ Email Verified</h1>
        <p>Your email has been successfully verified.</p>
        <p>You can now close this page and log in to <b>MarkMe</b>.</p>
    </div>
</body>
</html>
"""

ERROR_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Verification Failed</title>
</head>
<body style="font-family: Arial; text-align:center; margin-top:100px;">
    <h2>❌ Verification Failed</h2>
    <p>{message}</p>
</body>
</html>
"""


# ─────────────────────────────
# VERIFY EMAIL ENDPOINT
# ─────────────────────────────

async def verify_student_email(request_data: OtpRequest):
    try:
        email = request_data.email
        otp = request_data.otp

        # 1. Verify OTP
        is_valid, message = await verify_otp(email, otp)

        if not is_valid:
             return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "message": message
                }
            )

        # 2. Find Student
        student = await Student.find_one(Student.email == email)
        if not student:
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "message": "Student not found"
                }
            )

        # 3. Already verified
        if student.is_verified:
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "message": "Email already verified"
                }
            )

    

        # 5. Mark Verified
        student.is_verified = True
        student.verification_expires_at = None
        await student.save()

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Email verified successfully"
            }
        )

    except Exception as e:
        print(f"[verify_student_email] Error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"Server error: {str(e)}"
            }
        )
