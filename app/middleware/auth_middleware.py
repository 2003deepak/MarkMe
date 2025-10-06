from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from jose import jwt, JWTError
from datetime import datetime
from app.core.config import settings

class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, whitelist: list[str] = None):
        super().__init__(app)
        self.whitelist = whitelist or []  # Routes that do NOT require auth

    async def dispatch(self, request: Request, call_next):
        # Skip authentication for whitelisted routes
        if request.url.path not in self.whitelist:
            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                return JSONResponse(
                    status_code=401,
                    content={"status": "fail", "message": "Missing or invalid Authorization header"}
                )

            token = auth_header.split(" ")[1]

            try:
                payload = jwt.decode(
                    token,
                    settings.SECRET_KEY,
                    algorithms=[settings.ALGORITHM]
                )

                # Check token expiration
                if datetime.utcnow() > datetime.fromtimestamp(payload["exp"]):
                    return JSONResponse(
                        status_code=401,
                        content={"status": "fail", "message": "Token expired"}
                    )

                # Store decoded JWT in request.state
                request.state.user = payload

            except JWTError:
                return JSONResponse(
                    status_code=401,
                    content={"status": "fail", "message": "Invalid or expired token"}
                )

        # Continue to the route
        response = await call_next(request)
        return response
