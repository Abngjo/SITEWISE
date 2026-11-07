"""Photo metadata, authenticity and completion-phase checks. Providers are always mocked."""
import io
import json
import os
from datetime import datetime
from types import SimpleNamespace

import pytest
from PIL import Image
from PIL.TiffImagePlugin import IFDRational

# Set before importing any AI module, regardless of pytest collection order.
os.environ["SITEWISE_DISABLE_MODELS"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["SITEWISE_STATE_FILE"] = "/tmp/sitewise_test_state.json"

from fastapi.testclient import TestClient  # noqa: E402

from ai import inference  # noqa: E402
from backend.engines import photo_checks  # noqa: E402
from backend.main import app  # noqa: E402

client = TestClient(app)
NOW = datetime(2026, 11, 7, 10, 0)
PROJECT = {
    "current_certificate": "IPC-04",
    "certificates": [{"no": "IPC-03", "period_end": "2026-09-30"}, {"no": "IPC-04", "period_end": "2026-10-31"}],
    "site_location": {"lat": 25.1667, "lon": 51.6, "radius_km": 2},
}
ON_SITE = (25.17, 51.6)
DOHA = ("25.2854", "51.5310")


def _jpeg(taken=None, resaved=None, gps=None, make=None, model=None, software=None, seed=90):
    exif = Image.Exif()
    if resaved:
        exif[306] = resaved
    if make:
        exif[271] = make
    if model:
        exif[272] = model
    if software:
        exif[305] = software
    if taken:
        exif.get_ifd(0x8769)[36867] = taken
    if gps:
        block = exif.get_ifd(0x8825)
        block[1], block[2] = gps[0], tuple(IFDRational(x) for x in gps[1])
        block[3], block[4] = gps[2], tuple(IFDRational(x) for x in gps[3])
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (seed, 100, 110)).save(buf, "JPEG", exif=exif)
    return buf.getvalue()


def _inspect(meta_bytes=None, capture_time=None, time_source="exif", device=(None, None, None), project=PROJECT):
    meta = photo_checks.read_file(meta_bytes if meta_bytes is not None else _jpeg())
    return photo_checks.inspect(meta, capture_time, time_source, project, NOW, *device)


def _types(flags):
    return [f["type"] for f in flags]


# --------------------------------- reading the file ---------------------------------
def test_reads_original_capture_time_not_the_resaved_time():
    meta = photo_checks.read_file(_jpeg(taken="2026:10:15 09:50:00", resaved="2026:11:06 20:00:00"))
    assert meta["taken_at"] == "2026-10-15T09:50:00"


def test_reads_gps_camera_and_software():
    meta = photo_checks.read_file(_jpeg(gps=("N", (25, 10, 12), "E", (51, 36, 0)), make="Apple",
                                        model="iPhone 15", software="17.1"))
    assert meta["gps"] == pytest.approx((25.17, 51.6))
    assert meta["camera"] == "Apple iPhone 15"
    assert meta["software"] == "17.1"
    assert photo_checks.read_file(_jpeg(make="Canon", model="Canon EOS R5"))["camera"] == "Canon EOS R5"


def test_south_west_is_negative_and_no_fix_is_ignored():
    assert photo_checks.read_file(_jpeg(gps=("S", (1, 0, 0), "W", (2, 0, 0))))["gps"] == (-1.0, -2.0)
    assert photo_checks.read_file(_jpeg(gps=("N", (0, 0, 0), "E", (0, 0, 0))))["gps"] is None


@pytest.mark.parametrize("data", [b"", b"not an image", b"\xff\xd8\xff\xe1 broken"])
def test_unreadable_file_never_raises(data):
    assert photo_checks.read_file(data)["taken_at"] is None


# ------------------------------------- the flags -------------------------------------
def test_honest_live_photo_raises_nothing():
    photo = _jpeg(taken="2026:11:07 09:58:00", make="Apple", model="iPhone 15")
    meta, flags = _inspect(photo, "2026-11-07T10:00:00", "in_app_capture", (*ON_SITE, 12))
    assert flags == []
    assert meta["file_taken_at"] == "2026-11-07T09:58:00"
    assert meta["location"]["source"] == "device_at_upload"
    assert meta["location"]["distance_from_site_km"] < 1


def test_missing_metadata_is_flagged_without_doubling_the_existing_flag():
    assert _types(_inspect(capture_time="2026-11-07T10:00:00", time_source="in_app_capture")[1]) == ["no_camera_metadata"]
    assert _inspect(capture_time=None, time_source="missing")[1] == []  # timestamp_anomaly already covers this


def test_photo_from_before_the_certificate_period_is_flagged():
    photo = _jpeg(taken="2026:09:30 12:00:00")
    _, flags = _inspect(photo, "2026-09-30T12:00:00", "exif")
    assert _types(flags) == ["photo_predates_period"]
    assert "01 Oct 2026" in flags[0]["message"]
    assert _inspect(_jpeg(taken="2026:10:01 00:00:00"), "2026-10-01T00:00:00", "exif")[1] == []


def test_old_gallery_photo_on_the_upload_page_is_caught_by_its_file_date():
    photo = _jpeg(taken="2026:08:01 12:00:00")
    assert _types(_inspect(photo, "2026-11-07T10:00:00", "in_app_capture")[1]) == ["photo_predates_period"]


def test_gallery_photo_from_earlier_in_the_period_is_a_time_mismatch():
    photo = _jpeg(taken="2026:11:01 12:00:00")
    assert _types(_inspect(photo, "2026-11-07T10:00:00", "in_app_capture")[1]) == ["capture_time_mismatch"]
    near = _jpeg(taken="2026:11:07 09:05:00")
    assert _inspect(near, "2026-11-07T10:00:00", "in_app_capture")[1] == []


def test_future_date_is_flagged():
    assert _types(_inspect(_jpeg(taken="2027:01:01 12:00:00"), "2027-01-01T12:00:00", "exif")[1]) == ["photo_date_in_future"]


def test_first_certificate_has_no_earlier_period_to_compare():
    project = {**PROJECT, "current_certificate": "IPC-03"}
    assert _inspect(_jpeg(taken="2020:01:01 12:00:00"), "2020-01-01T12:00:00", "exif", project=project)[1] == []


def test_off_site_location_is_flagged_with_rounded_coordinates():
    photo = _jpeg(taken="2026:11:07 09:58:00")
    meta, flags = _inspect(photo, "2026-11-07T10:00:00", "in_app_capture", (*DOHA, "20"))
    assert _types(flags) == ["off_site"]
    assert meta["location"]["lat"] == 25.285 and meta["location"]["lon"] == 51.531
    assert meta["location"]["distance_from_site_km"] > 10


def test_poor_phone_accuracy_does_not_raise_a_false_off_site_flag():
    photo = _jpeg(taken="2026:11:07 09:58:00")
    assert _inspect(photo, "2026-11-07T10:00:00", "in_app_capture", ("25.195", "51.6", 5000))[1] == []


def test_photo_gps_wins_over_the_phone_location():
    photo = _jpeg(taken="2026:11:07 09:58:00", gps=("N", (25, 10, 12), "E", (51, 36, 0)))
    meta, flags = _inspect(photo, "2026-11-07T10:00:00", "in_app_capture", DOHA + (10,))
    assert meta["location"]["source"] == "photo_gps" and flags == []


@pytest.mark.parametrize("lat,lon", [("abc", "51"), ("nan", "51"), ("91", "51"), (None, None), ("0", "0")])
def test_bad_phone_location_is_ignored(lat, lon):
    assert _inspect(device=(lat, lon, None))[0]["location"] is None


def test_generator_tag_and_editing_software_are_flagged():
    photo = _jpeg(taken="2026:11:07 09:58:00") + b"digitalsourcetype/trainedAlgorithmicMedia"
    meta, flags = _inspect(photo, "2026-11-07T10:00:00", "in_app_capture")
    assert _types(flags) == ["authenticity_review"] and meta["ai_marker"]
    edited = _jpeg(taken="2026:11:07 09:58:00", software="Adobe Photoshop 25.0")
    assert _types(_inspect(edited, "2026-11-07T10:00:00", "in_app_capture")[1]) == ["authenticity_review"]
    phone = _jpeg(taken="2026:11:07 09:58:00", software="17.1")
    assert _inspect(phone, "2026-11-07T10:00:00", "in_app_capture")[1] == []


# ------------------------------------ through the API ------------------------------------
@pytest.fixture
def fresh():
    client.post("/api/admin/reset")
    yield
    client.post("/api/admin/reset")


def _upload(photo, **fields):
    return client.post("/api/evidence", files={"file": ("p.jpg", photo, "image/jpeg")},
                       data={"element_id": "D-104", **fields}).json()


def test_upload_returns_metadata_and_flags_without_changing_payment(fresh):
    before = client.get("/api/payments/audit").json()["totals"]
    r = _upload(_jpeg(taken="2026:08:01 12:00:00", make="Apple", model="iPhone 15", seed=20),
                capture_time="2026-11-07T10:00:00", time_source="in_app_capture", uploader="mobile",
                gps_lat=DOHA[0], gps_lon=DOHA[1], gps_accuracy_m="15")
    assert r["photo_meta"]["file_taken_at"] == "2026-08-01T12:00:00"
    assert r["photo_meta"]["camera"] == "Apple iPhone 15"
    assert r["photo_meta"]["location"]["source"] == "device_at_upload"
    assert {"photo_predates_period", "off_site"} <= set(_types(r["flags"]))
    assert all(f["evidence_id"] == r["evidence_id"] and f["element_id"] == "D-104" for f in r["flags"])
    assert client.get("/api/safety").json() == []  # for the engineer, not the safety officer's queue
    assert client.get("/api/payments/audit").json()["totals"] == before
    json.dumps(r)  # the record is saved as JSON


def test_desktop_upload_uses_the_files_original_time(fresh):
    r = _upload(_jpeg(taken="2026:10:15 09:50:00", resaved="2026:11:06 20:00:00", seed=30))
    assert r["capture_time"] == "2026-10-15T09:50:00" and r["time_source"] == "exif"


def test_no_metadata_upload_keeps_the_existing_flag_only(fresh):
    r = _upload(_jpeg(seed=40))
    assert _types(r["flags"]) == ["timestamp_anomaly"]
    assert r["photo_meta"]["has_camera_metadata"] is False


# --------------------------------------- the VLM ---------------------------------------
class FakeClient:
    def __init__(self, content):
        self.content, self.prompts, self.models = content, [], []

    def chat_completion(self, *, model, messages, **kwargs):
        self.models.append(model)
        self.prompts.append(messages[0]["content"][1]["text"])
        choice = SimpleNamespace(message=SimpleNamespace(content=self.content), finish_reason="stop")
        return SimpleNamespace(choices=[choice], usage=None)


def _vlm(monkeypatch, declared="door", claimed=True, **answer):
    import huggingface_hub
    body = {"label": "door", "completion": "partial", "reason": "Frame only.", **answer}
    fake = FakeClient(json.dumps(body))
    monkeypatch.setattr(huggingface_hub, "InferenceClient", lambda token=None: fake)
    return inference.stage2_vlm(Image.new("RGB", (32, 32)), declared, claimed), fake


def test_prompt_asks_the_new_questions_and_keeps_the_strict_completion_rule(monkeypatch):
    _, fake = _vlm(monkeypatch)
    prompt = fake.prompts[0]
    assert "frame_only" in prompt and "possibly_ai_generated" in prompt
    assert "a door frame without the door leaf is partial" in prompt
    _, fake = _vlm(monkeypatch, declared=None, claimed=False)
    assert "frame_only" not in fake.prompts[0] and "possibly_ai_generated" in fake.prompts[0]


def test_valid_extra_answers_are_kept(monkeypatch):
    res, _ = _vlm(monkeypatch, phase="frame_only", authenticity="possibly_edited", authenticity_reason=" Hard edges. ")
    assert (res["phase"], res["authenticity"], res["authenticity_reason"]) == ("frame_only", "possibly_edited", "Hard edges.")


@pytest.mark.parametrize("extras", [{}, {"phase": "made_up", "authenticity": "fake"},
                                    {"phase": ["frame_only"], "authenticity": 3, "authenticity_reason": 5}])
def test_bad_extra_answers_are_cleaned_without_using_the_fallback_model(monkeypatch, extras):
    res, fake = _vlm(monkeypatch, **extras)
    assert fake.models == [inference.VLM_MODEL]
    assert (res["phase"], res["authenticity"], res["authenticity_reason"]) == (None, "unclear", None)


def test_phase_is_dropped_when_the_photo_shows_something_else(monkeypatch):
    assert _vlm(monkeypatch, label="wall", phase="frame_only")[0]["phase"] is None


@pytest.mark.parametrize("completion,phase,kept", [
    ("partial", "complete_set", False), ("complete", "frame_only", False), ("unclear", "complete_set", False),
    ("partial", "frame_only", True), ("complete", "complete_set", True), ("complete", "leaf_hung", True),
])
def test_phase_that_contradicts_completion_is_dropped(monkeypatch, completion, phase, kept):
    res, _ = _vlm(monkeypatch, completion=completion, phase=phase)
    assert res["phase"] == (phase if kept else None)


def test_vision_model_suspicion_becomes_a_review_flag_and_looks_real_does_not(fresh, monkeypatch):
    answer = {"completion": "partial", "completion_pct": 50, "phase": None, "final_label": "door", "observations": [],
              "matches_declared_element": True, "requires_review": True, "completion_certified": False,
              "vlm": {"label": "door", "authenticity": "possibly_edited", "authenticity_reason": "Hard edges."}}
    monkeypatch.setattr(inference, "analyze", lambda *a, **k: answer)
    before = client.get("/api/payments/audit").json()["totals"]
    r = _upload(_jpeg(taken="2026:11:07 09:58:00", seed=50), capture_time="2026-11-07T10:00:00", time_source="in_app_capture")
    flag = next(f for f in r["flags"] if f["type"] == "authenticity_review")
    assert "edited" in flag["message"] and "Hard edges." in flag["message"] and "not proof" in flag["message"]
    assert client.get("/api/payments/audit").json()["totals"] == before
    answer["vlm"]["authenticity"] = "looks_real"
    r = _upload(_jpeg(taken="2026:11:07 09:58:00", seed=60), capture_time="2026-11-07T10:00:00", time_source="in_app_capture")
    assert "authenticity_review" not in _types(r["flags"])


def test_slab_keeps_its_phase_even_though_slab_is_not_a_label(monkeypatch):
    res, _ = _vlm(monkeypatch, declared="slab", label="other", phase="concrete_poured")
    assert res["phase"] == "concrete_poured"


@pytest.mark.parametrize("completion,pct", [("complete", 100), ("partial", 50), ("not_started", 0), ("unclear", None)])
def test_result_carries_percent_phase_and_authenticity_but_never_certifies(monkeypatch, completion, pct):
    import huggingface_hub
    body = {"label": "door", "completion": completion, "reason": "Seen.", "phase": "leaf_hung", "authenticity": "looks_real"}
    monkeypatch.setattr(huggingface_hub, "InferenceClient", lambda token=None: FakeClient(json.dumps(body)))
    monkeypatch.setattr(inference, "DISABLED", False)
    monkeypatch.setattr(inference, "stage1", lambda img: [{"label": k, "score": 0.9 if k == "door" else 0.03} for k in inference.LABELS])
    buf = io.BytesIO()
    Image.new("RGB", (32, 32)).save(buf, "JPEG")
    res = inference._analyze(buf.getvalue(), "PHOTO-T", "door", claimed_complete=True)
    assert (res["completion_pct"], res["phase"], res["authenticity"]) == (pct, "leaf_hung", "looks_real")
    assert res["completion_certified"] is False and res["requires_review"] is True
