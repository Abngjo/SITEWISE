"""Photo metadata checks for uploaded evidence (owner: Dev D).

Reads when, where and with what a photo was taken, then raises REVIEW FLAGS when something
doesn't add up. A flag is a prompt for the engineer, never a finding of fraud, and it never
changes payment. Metadata can be edited or stripped, so a clean result does not prove a photo
is genuine.
"""
from __future__ import annotations

import io
import math
import re
from datetime import date, datetime, timedelta

from PIL import Image

_EXIF_IFD, _GPS_IFD = 0x8769, 0x8825
_DATETIME_ORIGINAL, _DATETIME_DIGITIZED = 36867, 36868
_MAKE, _MODEL, _SOFTWARE, _DATETIME = 271, 272, 305, 306

TIME_MISMATCH = timedelta(minutes=60)  # page time vs file time on /m uploads
FUTURE_TOLERANCE = timedelta(days=1)   # file times carry no time zone
COORD_DECIMALS = 3                     # about 100 m: evidence is readable by anyone with the link

# Lower-case byte strings that generators and Content Credentials write into image files.
_AI_MARKERS = {
    b"trainedalgorithmicmedia": "an AI-generated media tag",
    b"midjourney": "Midjourney",
    b"stable diffusion": "Stable Diffusion",
    b"stablediffusion": "Stable Diffusion",
    b"dall-e": "DALL-E",
    b"dall\xc2\xb7e": "DALL-E",
    b"adobe firefly": "Adobe Firefly",
    b"comfyui": "ComfyUI",
    b"cfg scale:": "image generator settings",
}
_EDITORS = re.compile(r"photoshop|lightroom|gimp|snapseed|picsart|canva|pixelmator|facetune|affinity", re.I)


def _text(value) -> str | None:
    if isinstance(value, bytes):
        value = value.decode("utf-8", "ignore")
    cleaned = str(value).strip("\x00 ").strip() if value else ""
    return cleaned[:80] or None


def _exif_time(value) -> str | None:
    raw = _text(value)
    if not raw:
        return None
    try:
        return datetime.strptime(raw[:19], "%Y:%m:%d %H:%M:%S").isoformat()
    except ValueError:
        return None


def _valid_coords(lat, lon) -> tuple[float, float] | None:
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(lat) and math.isfinite(lon) and abs(lat) <= 90 and abs(lon) <= 180):
        return None
    return None if lat == 0 and lon == 0 else (lat, lon)  # 0,0 means the GPS had no fix


def _gps_degrees(parts, ref) -> float | None:
    try:
        degrees, minutes, seconds = (float(p) for p in parts)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    value = degrees + minutes / 60 + seconds / 3600
    return -value if (_text(ref) or "").upper() in ("S", "W") else value


def _distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def read_file(b: bytes) -> dict:
    """Facts from the image file itself. Never raises: an unreadable file just has no metadata."""
    low = b.lower()
    out = {"taken_at": None, "gps": None, "camera": None, "software": None,
           "ai_marker": next((name for marker, name in _AI_MARKERS.items() if marker in low), None)}
    try:
        with Image.open(io.BytesIO(b)) as im:
            exif = im.getexif()
            sub, gps = exif.get_ifd(_EXIF_IFD), exif.get_ifd(_GPS_IFD)
    except Exception:
        return out
    # DateTimeOriginal lives in the Exif sub-block. Top-level DateTime changes when a file is re-saved.
    out["taken_at"] = (_exif_time(sub.get(_DATETIME_ORIGINAL)) or _exif_time(sub.get(_DATETIME_DIGITIZED))
                       or _exif_time(exif.get(_DATETIME)))
    make, model = _text(exif.get(_MAKE)), _text(exif.get(_MODEL))
    out["camera"] = (model if make and model and model.lower().startswith(make.lower())
                     else " ".join(x for x in (make, model) if x) or None)
    out["software"] = _text(exif.get(_SOFTWARE))
    if gps.get(2) and gps.get(4):
        out["gps"] = _valid_coords(_gps_degrees(gps[2], gps.get(1)), _gps_degrees(gps[4], gps.get(3)))
    return out


def _period_start(project: dict) -> date | None:
    """First day of the current certificate's period: the day after the previous one ended."""
    certs = project.get("certificates") or []
    numbers = [c.get("no") for c in certs]
    current = project.get("current_certificate")
    if current not in numbers or numbers.index(current) == 0:
        return None
    return date.fromisoformat(certs[numbers.index(current) - 1]["period_end"]) + timedelta(days=1)


def _parse_iso(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value).replace(tzinfo=None) if value else None
    except ValueError:
        return None


def vlm_authenticity_flag(ai: dict) -> dict | None:
    """Turn the vision model's suspicion into a review flag. Its "looks_real" answer is not reassurance:
    see data/d_photo_checks/REPORT.md for how often it misses fakes."""
    vlm = ai.get("vlm") or {}
    what = {"possibly_edited": "edited", "possibly_ai_generated": "AI-generated"}.get(vlm.get("authenticity"))
    if not what:
        return None
    why = f" Its reason: {vlm['authenticity_reason']}" if vlm.get("authenticity_reason") else ""
    return {"type": "authenticity_review", "severity": "review",
            "message": f"The vision model thinks this photo may be {what}.{why} This is a guess, not proof. "
                       "Ask the contractor for the original."}


def inspect(file_meta: dict, capture_time: str | None, time_source: str, project: dict, now: datetime,
            device_lat=None, device_lon=None, device_accuracy_m=None) -> tuple[dict, list[dict]]:
    """Returns (photo_meta for the evidence record, review flags)."""
    flags = []

    def flag(kind: str, message: str):
        flags.append({"type": kind, "severity": "review", "message": message})

    taken = _parse_iso(file_meta["taken_at"])
    has_metadata = bool(taken or file_meta["camera"] or file_meta["gps"])
    if not has_metadata and time_source != "missing":  # "missing" already raises timestamp_anomaly
        flag("no_camera_metadata", "No camera metadata in this file, so it can't show when or where the photo "
             "was taken. This is common for screenshots, downloads and photos sent through messaging apps.")

    # A date typed by hand counts too. The /m page time is only the moment of upload, so it doesn't.
    photo_date = taken or (_parse_iso(capture_time) if time_source == "manual" else None)
    page_time = _parse_iso(capture_time) if time_source == "in_app_capture" else None
    start = _period_start(project)
    if photo_date and start and photo_date.date() < start:
        flag("photo_predates_period", f"Photo dated {photo_date:%d %b %Y}, before this certificate's period "
             f"starts on {start:%d %b %Y}. Check that it shows current work.")
    elif photo_date and photo_date > now + FUTURE_TOLERANCE:
        flag("photo_date_in_future", f"Photo dated {photo_date:%d %b %Y}, which is in the future. "
             "The camera clock may be wrong or the metadata may have been edited.")
    elif page_time and taken and abs(page_time - taken) > TIME_MISMATCH:
        flag("capture_time_mismatch", f"Uploaded {page_time:%d %b %H:%M}, but the file says it was taken "
             f"{taken:%d %b %H:%M}. It may have come from the gallery instead of being taken just now.")

    location = None
    coords, source, accuracy = file_meta["gps"], "photo_gps", None
    if not coords:
        coords, source = _valid_coords(device_lat, device_lon), "device_at_upload"
        try:
            accuracy = max(0.0, float(device_accuracy_m)) if coords and device_accuracy_m else None
        except (TypeError, ValueError):
            accuracy = None
    if coords:
        location = {"lat": round(coords[0], COORD_DECIMALS), "lon": round(coords[1], COORD_DECIMALS),
                    "source": source, "accuracy_m": round(accuracy) if accuracy is not None else None,
                    "distance_from_site_km": None}
        site = project.get("site_location")
        if site:
            distance = _distance_km(coords, (site["lat"], site["lon"]))
            location["distance_from_site_km"] = round(distance, 1)
            if distance > site.get("radius_km", 2) + (accuracy or 0) / 1000:
                where = "Photo GPS" if source == "photo_gps" else "The phone's location at upload"
                flag("off_site", f"{where} is about {distance:.1f} km from the project site. "
                     "Check that the photo shows this project.")

    if file_meta["ai_marker"]:
        flag("authenticity_review", f"The file's metadata mentions {file_meta['ai_marker']}, so this image may be "
             "AI-generated. Ask the contractor for the original.")
    elif _EDITORS.search(file_meta["software"] or ""):
        flag("authenticity_review", f"The file's metadata says it was saved by {file_meta['software']}, so this "
             "photo may have been edited. Ask the contractor for the original.")

    return {"file_taken_at": file_meta["taken_at"], "camera": file_meta["camera"],
            "software": file_meta["software"], "has_camera_metadata": has_metadata,
            "ai_marker": file_meta["ai_marker"], "location": location}, flags
