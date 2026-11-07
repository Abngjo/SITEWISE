"""SITEWISE API (owner: Dev C). Run: uvicorn backend.main:app --reload --port 7860

Endpoint contract lives in contracts/api.md. Do not change shapes without telling the team.
"""
from __future__ import annotations

import io
import sys
import uuid
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:  # load .env before importing modules that read env vars at import time
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from ai import duplicates, inference  # noqa: E402
from backend.engines import ask as ask_engine, bim, compliance, letter, payment, report, schedule  # noqa: E402
from backend.store import DATA_DIR, store  # noqa: E402

QATAR_TZ = ZoneInfo("Asia/Qatar")  # server runs in UTC; all timestamps shown in Doha time


def now_qatar() -> str:
    return datetime.now(QATAR_TZ).replace(tzinfo=None).isoformat(timespec="seconds")


UPLOAD_DIR = ROOT / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="SITEWISE API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---------- startup: index prior-certificate photos for reuse detection ----------
def _index_prior_photos():
    """Every image in data/sample_project/photos/<CERT>/ is registered as earlier evidence."""
    pdir = DATA_DIR / "photos"
    if not pdir.exists():
        return
    for cert_dir in sorted(p for p in pdir.iterdir() if p.is_dir()):
        if cert_dir.name == store.project["current_certificate"]:
            continue
        for f in sorted(cert_dir.iterdir()):
            if f.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                continue
            eid = f"PRIOR-{cert_dir.name}-{f.stem}"
            if eid in store.evidence:
                continue
            b = f.read_bytes()
            store.evidence[eid] = {
                "evidence_id": eid, "certificate_no": cert_dir.name, "filename": f.name,
                "path": str(f), "sha256": duplicates.sha256_bytes(b), "phash": duplicates.phash_bytes(b),
                "element_id": None, "prior": True, "embedding": inference.embed(b),
            }


_index_prior_photos()
WARMUP: dict = {}


@app.on_event("startup")
def _warm():
    """Load models once at boot; the first demo upload must not pay the load time."""
    WARMUP.update(inference.warm_up())
    for v in store.evidence.values():  # embeddings for prior photos once models are available
        if v.get("prior") and not v.get("embedding") and Path(v["path"]).exists():
            v["embedding"] = inference.embed(Path(v["path"]).read_bytes())


def _exif_time(b: bytes) -> str | None:
    try:
        exif = Image.open(io.BytesIO(b)).getexif()
        raw = exif.get(36867) or exif.get(306)  # DateTimeOriginal / DateTime
        if raw:
            return datetime.strptime(raw, "%Y:%m:%d %H:%M:%S").isoformat()
    except Exception:
        pass
    return None


# ------------------------------- read endpoints -------------------------------
@app.get("/api/health")
def health():
    return {"ok": True, "project_id": store.project["project_id"], "models": WARMUP}


@app.get("/api/project")
def get_project():
    return store.project


@app.get("/api/elements")
def get_elements():
    return [{**e, "status": store.element_status(eid), "review": store.reviews.get(eid),
             "evidence_ids": [k for k, v in store.evidence.items() if v.get("element_id") == eid]}
            for eid, e in store.elements.items()]


@app.get("/api/model/status")
def model_status():
    """For the 3D viewer: color by status. GLB node names == element_id."""
    return {eid: store.element_status(eid) for eid in store.elements}


@app.get("/api/model/overlay")
def model_overlay():
    """For the 3D heat view and evidence pins: QAR at risk per element (reconciles to the audit)
    and how many evidence photos are linked to each element."""
    risk = payment.element_risk(store.boq, store.elements, store.reviews, store.claims)
    counts: dict[str, int] = {}
    for e in store.evidence.values():
        if e.get("element_id") in store.elements:
            counts[e["element_id"]] = counts.get(e["element_id"], 0) + 1
    return {**risk, "evidence_counts": counts}


@app.get("/api/model/timeline")
def model_timeline():
    """Frames for the 3D replay: what was verified at each certificate, then this month's claim, then now."""
    certs = store.project.get("certificates", [])
    current = store.project["current_certificate"]
    frames = []
    for c in certs:
        if c["no"] == current:
            continue
        end = c["period_end"]
        st = {}
        for eid in store.elements:
            r = store.reviews.get(eid)
            ok = r and r["decision"] == "supported" and str(r.get("timestamp", ""))[:10] <= end
            st[eid] = "supported" if ok else "no_evidence"
        n = sum(v == "supported" for v in st.values())
        frames.append({"key": c["no"], "label": f"{c['no']} certified", "date": end, "status": st,
                       "caption": f"{n} of {len(st)} elements verified and paid by {end}"})
    cv = claim_view()
    frames.append({"key": f"{current}-claim", "label": f"{current} contractor's claim",
                   "date": store.project.get("as_of_date"),
                   "status": {k: ("no_evidence" if v == "not_claimed" else "supported") for k, v in cv.items()},
                   "caption": f"Contractor claims {sum(v != 'not_claimed' for v in cv.values())} of {len(cv)} elements done"})
    now = model_status()
    frames.append({"key": "verified-now", "label": "Verified by evidence (now)", "date": store.project.get("as_of_date"),
                   "status": now, "caption": f"Evidence supports {sum(v == 'supported' for v in now.values())} of {len(now)}"})
    return frames


@app.get("/api/model/claim-view")
def claim_view():
    """For the 3D 'contractor's claim' toggle: what the contractor says is done this certificate.
    claimed = claimed in the current certificate; certified = already paid in earlier certificates."""
    claimed = store.claimed_ids()
    prev = {c["boq_item_id"]: float(c["previous_certified_qty"]) for c in store.claims}
    out = {}
    for eid, e in store.elements.items():
        r = store.reviews.get(eid)
        if eid in claimed:
            out[eid] = "claimed"
        elif r and r["decision"] == "supported" and prev.get(e["boq_item_id"], 0) > 0:
            out[eid] = "certified"
        else:
            out[eid] = "not_claimed"
    return out


@app.get("/api/boq")
def get_boq():
    return list(store.boq.values())


@app.get("/api/evidence")
def list_evidence():
    return [{k: v for k, v in e.items() if k != "embedding"}
            for e in store.evidence.values() if not e.get("prior")]


@app.get("/api/evidence/{evidence_id}/image")
def evidence_image(evidence_id: str):
    ev = store.evidence.get(evidence_id)
    if not ev or not Path(ev["path"]).exists():
        raise HTTPException(404)
    return FileResponse(ev["path"])


@app.get("/api/payments/audit")
def payments_audit():
    return payment.audit(store.boq, store.elements, store.reviews, store.claims,
                         float(store.project.get("retention_pct", 0)))


@app.get("/api/schedule/forecast")
def schedule_forecast(delay_task: str | None = None, delay_days: float = 0):
    extra = {delay_task: delay_days} if delay_task else None
    fc = schedule.forecast(store.tasks, date.fromisoformat(store.project["start_date"]),
                           date.fromisoformat(store.project["as_of_date"]),
                           store.task_progress(), extra)
    rate = float(store.project.get("delay_damages_per_day_qar", 0))
    fc["delay_damages_per_day_qar"] = rate
    fc["delay_exposure_qar"] = round(max(0, fc["handover_delay_days"]) * rate, 2)
    fc["delay_damages_note"] = store.project.get("delay_damages_note", "")
    return fc


@app.get("/api/overview")
def overview():
    """One call for the dashboard landing page."""
    a, sc = payments_audit(), schedule_forecast()
    ev = [e for e in store.evidence.values() if not e.get("prior")]
    statuses = model_status()
    return {
        "project": store.project,
        "totals": a["totals"],
        "certificate_no": a["certificate_no"],
        "baseline_handover": sc["baseline_handover"],
        "forecast_handover": sc["forecast_handover"],
        "handover_delay_days": sc["handover_delay_days"],
        "delay_exposure_qar": sc["delay_exposure_qar"],
        "counts": {
            "photos_this_certificate": len(ev),
            "possible_reuse": sum(1 for e in ev if e.get("duplicates")),
            "flags_awaiting_review": len(store.safety),
            "elements": {k: list(statuses.values()).count(k)
                         for k in ("supported", "uncertain", "discrepancy", "no_evidence")},
        },
        "ai": {k: v for k, v in inference.cost_summary().items() if k != "log"},
    }


@app.get("/api/safety")
def safety():
    return store.safety


@app.get("/api/ai/costs")
def ai_costs():
    return inference.cost_summary()


@app.get("/api/report")
def get_report(lang: str = "en"):
    dup_flags = [e for e in store.evidence.values() if e.get("duplicates")]
    return report.build(store.project, payments_audit(), schedule_forecast(), store.safety,
                        dup_flags, inference.cost_summary(), lang)


# ------------------------------------ BIM -------------------------------------
_BIM_CACHE: dict = {}


def _bim_summary() -> dict:
    if "default" not in _BIM_CACHE:
        try:
            _BIM_CACHE["default"] = bim.parse(DATA_DIR / "project.ifc", store.elements)
        except Exception as e:
            return {"error": f"IFC parse failed: {e}"}
    return _BIM_CACHE["default"]


@app.get("/api/bim/summary")
def bim_summary():
    """Parsed live from data/sample_project/project.ifc with IfcOpenShell."""
    s = _bim_summary()
    return {k: v for k, v in s.items() if k != "elements"}


@app.get("/api/bim/elements")
def bim_elements():
    return _bim_summary().get("elements", [])


@app.get("/api/bim/elements/{element_id}")
def bim_element(element_id: str):
    for r in _bim_summary().get("elements", []):
        if r["element_id"] == element_id:
            return {**r, "status": store.element_status(element_id),
                    "record": store.elements.get(element_id)}
    raise HTTPException(404)


@app.get("/api/bim/export")
def bim_export():
    """Download the BIM with SITEWISE evidence written into each element (Pset 'SITEWISE_Evidence')."""
    cert = store.project.get("current_certificate", "IPC")
    out = UPLOAD_DIR / f"sitewise_as_verified_{cert}.ifc"
    try:
        bim.export_as_verified(DATA_DIR / "project.ifc", out, store, payments_audit())
    except Exception as e:
        raise HTTPException(500, f"IFC export failed: {e}")
    return FileResponse(out, media_type="application/x-step", filename=out.name)


@app.post("/api/bim/import")
async def bim_import(file: UploadFile = File(...)):
    """Upload any IFC: SITEWISE extracts its elements and reports how they map to BOQ + schedule.
    (Demo: does not replace the project model.)"""
    b = await file.read()
    if not b.startswith(b"ISO-10303-21"):
        raise HTTPException(400, "Not an IFC (STEP) file")
    tmp = UPLOAD_DIR / f"import-{uuid.uuid4().hex[:6]}.ifc"
    tmp.write_bytes(b)
    try:
        s = bim.parse(tmp, store.elements)
    except Exception as e:
        raise HTTPException(400, f"IFC parse failed: {e}")
    return {k: v for k, v in s.items() if k != "elements"} | {"elements_preview": s["elements"][:30]}


@app.get("/api/audit-letter")
def audit_letter(lang: str = "en"):
    """Draft letter to the contractor. Figures from code; LLM only writes the opening paragraph."""
    return letter.build(store, payments_audit(), "ar" if lang == "ar" else "en")


# ------------------------------- write endpoints ------------------------------
@app.post("/api/evidence")
async def upload_evidence(
    file: UploadFile = File(...),
    element_id: str | None = Form(None),
    capture_time: str | None = Form(None),       # ISO; set by the in-app camera page
    time_source: str = Form("exif"),             # in_app_capture | exif | manual
    uploader: str = Form("contractor"),
):
    b = await file.read()
    if not b:
        raise HTTPException(400, "empty file")
    if element_id and element_id not in store.elements:
        raise HTTPException(404, f"unknown element {element_id}")
    eid = f"PHOTO-{uuid.uuid4().hex[:8].upper()}"
    path = UPLOAD_DIR / f"{eid}{Path(file.filename or 'x.jpg').suffix or '.jpg'}"
    path.write_bytes(b)

    if not capture_time:
        capture_time = _exif_time(b)
        time_source = "exif" if capture_time else "missing"

    rec = {
        "evidence_id": eid, "certificate_no": store.project["current_certificate"],
        "filename": file.filename, "path": str(path), "element_id": element_id,
        "capture_time": capture_time, "time_source": time_source,
        "upload_time": now_qatar(), "uploader": uploader,
        "sha256": duplicates.sha256_bytes(b), "phash": duplicates.phash_bytes(b),
        "embedding": inference.embed(b),
    }
    rec["duplicates"] = duplicates.find_duplicates(rec, list(store.evidence.values()))

    declared = store.elements[element_id]["type"] if element_id else None
    try:
        rec["ai"] = inference.analyze(b, eid, declared,
                                      claimed_complete=bool(element_id) and element_id in store.claimed_ids())
    except Exception as e:  # never 500 during the demo: store evidence, send to human review
        rec["ai"] = {"evidence_id": eid, "model_id": None, "observations": [], "final_label": None,
                     "vlm": None, "matches_declared_element": None, "requires_review": True,
                     "completion_certified": False, "error": f"AI unavailable: {e}",
                     "latency_s": 0.0, "est_cost_usd": 0.0}

    flags = []
    if element_id:
        f = compliance.summer_hours_flag(capture_time, store.elements[element_id]["calendar"], time_source)
        if f:
            flags.append({**f, "evidence_id": eid, "element_id": element_id})
    if time_source == "missing":
        flags.append({"type": "timestamp_anomaly", "severity": "review", "evidence_id": eid,
                      "message": "No capture time available for this photo."})
    store.safety.extend(flags)
    rec["flags"] = flags

    store.evidence[eid] = rec
    store.save()
    return {k: v for k, v in rec.items() if k != "embedding"}


class Question(BaseModel):
    question: str
    lang: str = "en"


@app.post("/api/ask")
def ask_sitewise(q: Question):
    """Grounded Q&A: Gemma answers from computed project data; every figure is verified before display."""
    if not q.question.strip():
        raise HTTPException(400, "empty question")
    ctx = ask_engine.context(store, payments_audit(), schedule_forecast(), overview())
    return ask_engine.ask(q.question.strip()[:500], ctx, "ar" if q.lang == "ar" else "en")


class Review(BaseModel):
    decision: str                  # supported | partial | uncertain | rejected
    supported_qty: float | None = None
    reason: str = ""
    reviewer: str = "Site engineer"
    evidence_id: str | None = None


@app.post("/api/elements/{element_id}/review")
def review_element(element_id: str, r: Review):
    if element_id not in store.elements:
        raise HTTPException(404)
    if r.decision not in {"supported", "partial", "uncertain", "rejected"}:
        raise HTTPException(400, "bad decision")
    store.reviews[element_id] = {
        "element_id": element_id, "decision": r.decision,
        "supported_qty": r.supported_qty if r.supported_qty is not None else (
            store.elements[element_id]["quantity"] if r.decision == "supported" else 0),
        "reason": r.reason, "reviewer": r.reviewer, "evidence_id": r.evidence_id,
        "timestamp": now_qatar(),
    }
    store.save()
    # Return everything the UI must refresh after one decision (the "judge moment").
    return {"element": {**store.elements[element_id], "status": store.element_status(element_id)},
            "model_status": model_status(), "audit": payments_audit(), "schedule": schedule_forecast()}


@app.post("/api/admin/reset")
def reset_demo():
    """Reset to seed data before each rehearsal / the live demo."""
    from backend.store import STATE_FILE
    if STATE_FILE.exists():
        STATE_FILE.unlink()
    inference.COST_LOG.clear()
    inference._CACHE.clear()
    store.reset()
    _index_prior_photos()
    return {"ok": True}


# ------------------------------- static frontend ------------------------------
MOBILE = ROOT / "frontend" / "mobile_upload.html"


@app.get("/m")
def mobile_upload():
    return FileResponse(MOBILE)


@app.get("/model.glb")
def model_glb():
    for p in (ROOT / "frontend" / "dist" / "model.glb", ROOT / "frontend" / "public" / "model.glb"):
        if p.exists():
            return FileResponse(p, media_type="model/gltf-binary")
    raise HTTPException(404, "run scripts/ifc_to_glb.py")


DIST = ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="frontend")
else:
    @app.get("/")
    def root():
        return {"msg": "SITEWISE API running. Frontend not built yet. See /docs and /m"}
