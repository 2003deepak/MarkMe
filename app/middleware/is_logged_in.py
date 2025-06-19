from datetime import datetime
from fastapi import Request, HTTPException, status
from jose import JWTError, jwt
from typing import Dict, Any
from app.core.config import settings

async def is_logged_in(request: Request) -> Dict[str, Any]:
    auth_header = request.headers.get("Authorization")
    
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={"status": "fail", "message": "Missing or invalid Authorization header"},
        )

    token = auth_header.split(" ")[1]
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"verify_aud": False},  # Disable if you don’t use "aud" claim
        )
        
        # Explicitly check expiration (redundant but clear)
        if datetime.utcnow() > datetime.fromtimestamp(payload["exp"]):
            raise HTTPException(
                status_code=401,
                detail={"status": "fail", "message": "Token expired"},
            )

        return payload

    except JWTError as e:
        raise HTTPException(
            status_code=401,
            detail={"status": "fail", "message": "Invalid or expired token"},
        )