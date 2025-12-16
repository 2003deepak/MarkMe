from typing import List, Optional
from zoneinfo import ZoneInfo
from datetime import datetime, timezone


def parse_comma_separated_list(value: Optional[str]) -> Optional[List[str]]:
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


IST = ZoneInfo("Asia/Kolkata")

def to_ist(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST)