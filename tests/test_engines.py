"""Acceptance tests from the plan. Run: SITEWISE_DISABLE_MODELS=1 pytest -q
Dev D: recompute the payment numbers by hand in a spreadsheet; both must match.
"""
import io
import os
from datetime import date

os.environ["SITEWISE_DISABLE_MODELS"] = "1"
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


# ---------------- completion check + audit letter ----------------
def test_claimed_element_triggers_completion_check():
    r = client.post("/api/evidence", files={"file": ("d.jpg", _img((90, 90, 200)), "image/jpeg")},
                    data={"element_id": "D-201"}).json()
    assert r["ai"]["claimed_complete"] is True        # D-201 is claimed in IPC-04
    r2 = client.post("/api/evidence", files={"file": ("e.jpg", _img((200, 200, 90)), "image/jpeg")},
                     data={"element_id": "C-201"}).json()
    assert r2["ai"]["claimed_complete"] is False      # C-201 not claimed this period


def test_audit_letter_en_ar_same_figures_and_findings():
    en = client.get("/api/audit-letter?lang=en").json()
    ar = client.get("/api/audit-letter?lang=ar").json()
    assert en["figures"] == ar["figures"]
    assert len(en["items"]) == len(ar["items"]) > 0
    assert any("C-102" in i for i in en["items"])     # claimed, no photo
    assert "QAR 98,520" in en["summary"] and "QAR 98,520" in ar["summary"]
    assert ar["direction"] == "rtl"
    assert not any(ch.isdigit() for ch in en["opening"])  # opening paragraph never carries figures


# ---------------- BIM ----------------
def test_bim_summary_parsed_from_ifc():
    s = client.get("/api/bim/summary").json()
    assert s["schema"] == "IFC4"
    assert s["mapped_elements"] == 22 and s["context_elements"] >= 30
    assert s["total_elements"] == s["mapped_elements"] + s["context_elements"]
    assert not s["unmapped_ifc_elements"] and not s["sitewise_records_missing_in_ifc"]
    assert s["element_counts"]["IfcDoor"] == 9 and s["element_counts"]["IfcWindow"] > 0
    assert [x["name"] for x in s["storeys"]] == ["L1", "L2"]
    e = client.get("/api/bim/elements/D-103").json()
    assert e["ifc_class"] == "IfcDoor" and e["storey"] == "L1" and e["boq_item_id"] == "BOQ-DR-01"


def test_bim_import_roundtrip():
    from backend.store import DATA_DIR
    b = (DATA_DIR / "project.ifc").read_bytes()
    r = client.post("/api/bim/import", files={"file": ("x.ifc", b, "application/octet-stream")}).json()
    assert r["mapped_elements"] == 22
    bad = client.post("/api/bim/import", files={"file": ("x.ifc", b"hello", "application/octet-stream")})
    assert bad.status_code == 400


def test_claim_view_and_as_verified_export():
    cv = client.get("/api/model/claim-view").json()
    assert cv["D-201"] == "claimed" and cv["C-201"] == "not_claimed"
    client.post("/api/elements/D-103/review", json={"decision": "supported", "reason": "ok"})
    r = client.get("/api/bim/export")
    assert r.status_code == 200 and r.content.startswith(b"ISO-10303-21")
    import ifcopenshell, ifcopenshell.util.element as U, tempfile, os
    p = os.path.join(tempfile.mkdtemp(), "x.ifc"); open(p, "wb").write(r.content)
    f = ifcopenshell.open(p)
    door = [e for e in f.by_type("IfcDoor") if e.Tag == "D-103"][0]
    ps = U.get_psets(door)["SITEWISE_Evidence"]
    assert ps["EvidenceStatus"] == "supported" and ps["SupportedValueQAR"] == 6500
    assert ps["ClaimedThisCertificate"] is True


def test_timeline_and_delay_exposure():
    fr = client.get("/api/model/timeline").json()
    keys = [f["key"] for f in fr]
    assert keys[0] == "IPC-01" and keys[-1] == "verified-now" and "IPC-04-claim" in keys
    ipc2 = [f for f in fr if f["key"] == "IPC-02"][0]["status"]
    assert ipc2["S-101"] == "supported" and ipc2["W-101"] == "no_evidence"
    ipc3 = [f for f in fr if f["key"] == "IPC-03"][0]["status"]
    assert ipc3["W-101"] == "supported" and ipc3["D-101"] == "no_evidence"
    fc = client.get("/api/schedule/forecast").json()
    assert fc["delay_exposure_qar"] == max(0, fc["handover_delay_days"]) * 1800
    assert client.get("/api/report").json()["figures"]["delay_exposure_qar"] == fc["delay_exposure_qar"]


def test_ask_grounding_check():
    from backend.engines import ask as A
    from backend.main import overview, payments_audit, schedule_forecast
    ctx = A.context(store, payments_audit(), schedule_forecast(), overview())
    ok, bad = A.grounded("The gap is QAR 98,520 and C-102 (QAR 25,200) has no photo; IPC-04 on 2026-11-07, L2.", ctx)
    assert ok, bad
    ok, bad = A.grounded("The gap is QAR 98,999.", ctx)
    assert not ok and 98999.0 in bad
    ok, _ = A.grounded("الفرق ٩٨٥٢٠ ريال", ctx)  # Arabic-Indic digits normalised
    assert ok
    r = client.post("/api/ask", json={"question": "What is the gap?"}).json()
    assert "answer" in r  # models disabled in tests -> graceful message


def test_model_overlay_reconciles_with_audit():
    o = client.get("/api/model/overlay").json()
    a = client.get("/api/payments/audit").json()
    assert abs(o["total_at_risk"] - a["totals"]["discrepancy"]) < 0.05
    assert all(v["at_risk"] >= 0 for v in o["elements"].values())
    assert not any(k.startswith("CTX-") for k in o["elements"])
