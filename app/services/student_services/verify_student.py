from fastapi import Request
from fastapi.responses import HTMLResponse
from jose import JWTError
from app.utils.token_utils import decode_verification_token
from app.schemas.student import Student

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

async def verify_student_email(request: Request):
    try:
        # 1️⃣ Get token
        token = request.query_params.get("token")
        if not token:
            return HTMLResponse(
                ERROR_HTML.format(message="Verification token is missing."),
                status_code=400
            )

        # 2️⃣ Decode token
        email = decode_verification_token(token)

        # 3️⃣ Find student
        student = await Student.find_one(Student.email == email)
        if not student:
            return HTMLResponse(
                ERROR_HTML.format(message="Student not found."),
                status_code=404
            )

        # 4️⃣ Already verified
        if student.is_verified:
            return HTMLResponse(
                SUCCESS_HTML,
                status_code=200
            )

        # 5️⃣ Verify student
        student.is_verified = True
        student.verification_expires_at = None
        await student.save()

        # 6️⃣ Success page
        return HTMLResponse(
            SUCCESS_HTML,
            status_code=200
        )

    except JWTError:
        return HTMLResponse(
            ERROR_HTML.format(message="Invalid or expired verification link."),
            status_code=400
        )

    except Exception as e:
        print(f"[verify_student_email] Error: {str(e)}")
        return HTMLResponse(
            ERROR_HTML.format(message="Something went wrong. Please try again later."),
            status_code=500
        )
