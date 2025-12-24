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

def _build_swap_payload(swap):
    if not swap:
        return None

    return {
        "swap_id": str(swap["_id"]),
        "status": swap.get("status"),
        "requested_by": {
            "teacher_id": str(swap["requested_by"].id) if swap.get("requested_by") else None
        },
        "requested_to": {
            "teacher_id": str(swap["requested_to"].id) if swap.get("requested_to") else None
        },
        "source_session_id": (
            str(swap["source_session"].id)
            if swap.get("source_session") else None
        ),
        "target_session_id": (
            str(swap["target_session"].id)
            if swap.get("target_session") else None
        ),
        "responded_at": (
            swap["responded_at"].isoformat()
            if swap.get("responded_at") else None
        )
    }
