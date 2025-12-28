from typing import List, Optional
from zoneinfo import ZoneInfo
from datetime import datetime, timezone

from fastapi.responses import JSONResponse


def parse_comma_separated_list(value: Optional[str]) -> Optional[List[str]]:
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]

def overlap_error_response(count: int):
    return JSONResponse(
        status_code=409,
        content={
            "success": False,
            "code": "MULTIPLE_OVERLAPS",
            "message": (
                f"Session overlaps with {count} existing sessions. "
                "Swap is allowed only when overlapping with exactly one session."
            )
        }
    )


IST = ZoneInfo("Asia/Kolkata")

def to_ist(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST)