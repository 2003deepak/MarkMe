import json
import secrets
from typing import Tuple
from app.core.redis import get_redis_client


OTP_LENGTH = 6
OTP_TTL_SECONDS = 300           # 5 minutes
MAX_VERIFY_ATTEMPTS = 5

SEND_WINDOW_SECONDS = 3600      # 1 hour
MAX_OTP_SENDS = 5


# HELPERS
def _otp_key(email: str) -> str:
    return f"email_otp:{email}"


def _send_key(email: str) -> str:
    return f"email_otp_send:{email}"


def generate_6_digit_otp() -> str:
    return f"{secrets.randbelow(10 ** OTP_LENGTH):0{OTP_LENGTH}d}"


# OTP SEND (RATE LIMITED)
async def generate_and_store_otp(email: str) -> str:
  
    send_key = _send_key(email)
    redis = await get_redis_client()

    # rate limit send
    send_count = await redis.incr(send_key)
    if send_count == 1:
        await redis.expire(send_key, SEND_WINDOW_SECONDS)

    if send_count > MAX_OTP_SENDS:
        raise ValueError("Too many OTP requests. Please try again later.")

    otp = generate_6_digit_otp()

    otp_data = {
        "otp": otp,
        "attempts": 0
    }

    await redis.setex(
        _otp_key(email),
        OTP_TTL_SECONDS,
        json.dumps(otp_data)
    )

    return otp

# OTP VERIFY
async def verify_otp(email: str, submitted_otp: str) -> Tuple[bool, str]:

    key = _otp_key(email)
    
    redis = await get_redis_client()
    raw = await redis.get(key)

    if not raw:
        return False, "OTP expired or not found"

    data = json.loads(raw)

    # too many attempts
    if data["attempts"] >= MAX_VERIFY_ATTEMPTS:
        await redis.delete(key)
        return False, "Too many invalid attempts. OTP locked."

    # match
    if data["otp"] != submitted_otp:
        data["attempts"] += 1
        await redis.setex(
            key,
            OTP_TTL_SECONDS,
            json.dumps(data)
        )
        return False, "Invalid OTP"

    # success
    await redis.delete(key)
    return True, "OTP verified successfully"
