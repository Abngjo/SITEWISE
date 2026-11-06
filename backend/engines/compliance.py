"""Safety & compliance flags (owner: Dev C; PPE observations come from Dev A).

Everything here produces REVIEW FLAGS for a safety officer, never violations.
A timestamp alone does not prove work happened or that metadata is authentic.
"""
from __future__ import annotations

from datetime import datetime, time

from .schedule import in_summer_window

BAN_START = time(10, 0)
BAN_END = time(15, 30)


def summer_hours_flag(capture_time: str | None, calendar: str, time_source: str) -> dict | None:
    """Flag outdoor evidence captured inside the summer midday restriction window."""
    if not capture_time or calendar != "outdoor":
        return None  # indoor / ventilated work is out of scope of this rule
    try:
        dt = datetime.fromisoformat(capture_time)
    except ValueError:
        return {"type": "timestamp_anomaly", "severity": "review",
                "message": f"Unparseable capture time: {capture_time}"}
    if in_summer_window(dt.date()) and BAN_START <= dt.time() <= BAN_END:
        return {
            "type": "summer_working_hours",
            "severity": "review",
            "message": (f"Outdoor activity evidence captured {dt:%d %b %H:%M}, inside the "
                        "1 Jun-15 Sep 10:00-15:30 restriction window. Check whether work was "
                        "performed and whether an exemption applies."),
            "time_source": time_source,  # 'in_app_capture' is more trustworthy than 'exif'
        }
    return None


def ppe_flags(observations: list[dict], threshold: float = 0.4) -> list[dict]:
    """Turn PPE-related model observations into review flags (if Dev A adds a PPE model)."""
    flags = []
    for o in observations:
        if o.get("label") in {"person_without_hardhat", "person_without_vest"} and o.get("score", 0) >= threshold:
            flags.append({"type": "ppe", "severity": "review",
                          "message": f"Possible PPE concern: {o['label']} ({o['score']:.2f})"})
    return flags
