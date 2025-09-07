from jose import JWTError, jwt
from datetime import datetime, timedelta
from app.core.config import settings


def create_verification_token(email: str) -> str:
    """
    Generates a JWT token with user email and expiry time.
    """
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": email, "exp": expire}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def decode_verification_token(token: str) -> str:
    """
    Decodes JWT and returns email if valid.
    Raises JWTError if invalid/expired.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise JWTError("Invalid token payload")
        return email
    except JWTError as e:
        raise e
