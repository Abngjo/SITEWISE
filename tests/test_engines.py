"""Acceptance tests from the plan. Run: SITEWISE_DISABLE_MODELS=1 pytest -q
Dev D: recompute the payment numbers by hand in a spreadsheet; both must match.
"""
import io
import os
from datetime import date

os.environ["SITEWISE_DISABLE_MODELS"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["SITEWISE_STATE_FILE"] = "/tmp/sitewise_test_state.json"

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from backend.engines import compliance, payment, schedule  # noqa: E402
from backend.main import app  # noqa: E402
from backend.store import store  # noqa: E402

client = TestClient(app)


def setup_function():
    client.post("/api/admin/reset")


# ---------------- payment ----------------
def test_seed_payment_figures():
    a = payment.audit(store.boq, store.elements, store.reviews, store.claims, 10)
    items = {i["boq_item_id"]: i for i in a["items"]}
    # Blockwork: claimed 220 m2 x 95 = 20,900; supported (L2 W-201+W-202 = 124 m2) x 95 = 11,780
    assert items["BOQ-BW-01"]["claimed_value_this_period"] == 20900
    assert items["BOQ-BW-01"]["supported_value_this_period"] == 11780
    # Doors: claimed 8 x 6,500 = 52,000; supported 2 x 6,500 = 13,000
    assert items["BOQ-DR-01"]["discrepancy"] == 39000
    # Ceilings: claimed 360 m2 x 140 = 50,400; supported 0
    assert items["BOQ-CL-01"]["discrepancy"] == 50400
    # Structure already fully certified -> nothing claimed this period
    assert items["BOQ-ST-01"]["claimed_value_this_period"] == 0
    assert a["totals"]["claimed_this_period"] == 123300
    assert a["totals"]["supported_this_period"] == 24780
    assert a["totals"]["discrepancy"] == 98520


def test_unsupported_flagged_not_rejected():
    a = client.get("/api/payments/audit").json()
    cl = [i for i in a["items"] if i["boq_item_id"] == "BOQ-CL-01"][0]
    assert cl["status"] == "insufficient_evidence"
    assert "C-102" in cl["claimed_without_evidence"]


def test_review_updates_everything():
    before = client.get("/api/payments/audit").json()["totals"]["supported_this_period"]
    r = client.post("/api/elements/D-103/review", json={"decision": "supported", "reason": "leaf installed"}).json()
    assert r["model_status"]["D-103"] == "supported"
    assert r["audit"]["totals"]["supported_this_period"] == before + 6500
    rep = client.get("/api/report?lang=ar").json()
    assert rep["figures"]["supported_this_period"] == before + 6500


# ---------------- schedule ----------------
def _fc(**kw):
    return client.get("/api/schedule/forecast", params=kw).json()


def test_critical_delay_moves_handover_float_task_does_not():
    base = _fc()
    crit = base["critical_path"]
    noncrit = [t for t in base["tasks"] if not t["critical"] and not t["complete"]
               and t["total_float_days"] and t["total_float_days"] > 5]
    assert crit, "expected a critical path"
    assert noncrit, "expected at least one task with float"
    critical_task = [t for t in crit if t not in ("T-900",)][0]
    d1 = _fc(delay_task=critical_task, delay_days=5)
    assert d1["forecast_handover"] > base["forecast_handover"]
    d2 = _fc(delay_task=noncrit[0]["task_id"], delay_days=2)
    assert d2["forecast_handover"] == base["forecast_handover"]


def test_summer_calendar_slows_outdoor_only():
    s = date(2026, 7, 4)  # Saturday, inside the summer window
    assert schedule.advance(s, 10, "outdoor") > schedule.advance(s, 10, "indoor")
    w = date(2026, 11, 7)
    assert schedule.advance(w, 10, "outdoor") == schedule.advance(w, 10, "indoor")


def test_friday_is_not_a_working_day():
    assert schedule.capacity(date(2026, 11, 6), "indoor") == 0  # Friday


# ---------------- compliance ----------------
def test_summer_hours_flags_outdoor_not_indoor():
    assert compliance.summer_hours_flag("2026-07-12T12:30:00", "outdoor", "exif")["type"] == "summer_working_hours"
    assert compliance.summer_hours_flag("2026-07-12T12:30:00", "indoor", "exif") is None
    assert compliance.summer_hours_flag("2026-07-12T08:00:00", "outdoor", "exif") is None
    assert compliance.summer_hours_flag("2026-11-02T12:30:00", "outdoor", "exif") is None


# ---------------- evidence / duplicates ----------------
def _img(color=(120, 90, 60), size=(640, 480)):
    im = Image.new("RGB", size, color)
    for x in range(0, size[0], 40):
        for y in range(0, size[1], 40):
            if (x // 40 + y // 40) % 3 == 0:
                im.putpixel((x, y), (255, 255, 255))
                Image.Image.paste(im, (230, 230, 230), (x, y, x + 20, y + 20))
    b = io.BytesIO()
    im.save(b, format="JPEG", quality=92)
    return b.getvalue()


def test_exact_and_resized_duplicates():
    img = _img()
    r1 = client.post("/api/evidence", files={"file": ("a.jpg", img, "image/jpeg")},
                     data={"element_id": "D-104"}).json()
    r2 = client.post("/api/evidence", files={"file": ("b.jpg", img, "image/jpeg")},
                     data={"element_id": "D-104"}).json()
    assert r2["duplicates"][0]["evidence_id"] == r1["evidence_id"]
    assert r2["duplicates"][0]["kind"] == "exact"
    small = io.BytesIO()
    Image.open(io.BytesIO(img)).resize((320, 240)).save(small, format="JPEG", quality=70)
    r3 = client.post("/api/evidence", files={"file": ("c.jpg", small.getvalue(), "image/jpeg")},
                     data={"element_id": "D-104"}).json()
    assert any(d["kind"] == "near_duplicate_phash" for d in r3["duplicates"])


def test_ai_never_certifies_and_missing_time_flagged():
    r = client.post("/api/evidence", files={"file": ("x.jpg", _img((10, 120, 200)), "image/jpeg")},
                    data={"element_id": "C-102"}).json()
    assert r["ai"]["completion_certified"] is False
    assert r["ai"]["requires_review"] is True
    assert any(f["type"] == "timestamp_anomaly" for f in r["flags"])
    assert client.get("/api/model/status").json()["C-102"] == "uncertain"


# ---------------- C6/C7 additions ----------------
def test_overview_one_call():
    o = client.get("/api/overview").json()
    assert o["totals"]["discrepancy"] == 98520
    assert o["counts"]["elements"]["discrepancy"] > 0
    assert "forecast_handover" in o


def test_ai_failure_is_graceful(monkeypatch):
    from ai import inference

    def boom(*a, **k):
        raise RuntimeError("provider down")
    monkeypatch.setattr(inference, "analyze", boom)
    r = client.post("/api/evidence", files={"file": ("f.jpg", _img((200, 10, 10)), "image/jpeg")},
                    data={"element_id": "D-104"})
    assert r.status_code == 200
    assert r.json()["ai"]["requires_review"] is True
    assert "AI unavailable" in r.json()["ai"]["error"]


def test_identical_photo_uses_cache():
    img = _img((30, 160, 90))
    client.post("/api/evidence", files={"file": ("a.jpg", img, "image/jpeg")}, data={"element_id": "W-203"})
    r2 = client.post("/api/evidence", files={"file": ("b.jpg", img, "image/jpeg")}, data={"element_id": "W-203"}).json()
    assert r2["ai"].get("cache_hit") is True
    assert client.get("/api/ai/costs").json()["cache_hits"] >= 1
