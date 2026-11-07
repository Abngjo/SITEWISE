"""A5 cost logging and successful-result cache tests; no network or models."""
import io
import os

import pytest
from PIL import Image

# Preserve the official suite's no-model/no-provider collection mode regardless
# of which test module pytest imports first. Individual tests monkeypatch the
# module flag only around their fully mocked calls.
os.environ["SITEWISE_DISABLE_MODELS"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

from ai import inference


def _image_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (32, 32), (40, 120, 200)).save(output, format="JPEG")
    return output.getvalue()


def _observations():
    return [
        {"label": "door", "score": 0.55},
        {"label": "other", "score": 0.25},
        {"label": "wall", "score": 0.15},
        {"label": "ceiling", "score": 0.05},
    ]


def _call(model, *, cost=.001, confirmed=None, input_tokens=12, output_tokens=3, error=None):
    return {
        "model": model, "latency_s": .2,
        "input_tokens": input_tokens, "output_tokens": output_tokens,
        "estimated_cost_usd": 0.0 if confirmed is not None else cost,
        "provider_reported_cost_usd": None,
        "provider_confirmed_cost_usd": confirmed,
        "cost_source": "provider_confirmed" if confirmed is not None else "estimated",
        "error": error,
    }


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    inference._CACHE.clear()
    inference.COST_LOG.clear()
    monkeypatch.setattr(inference, "DISABLED", False)
    monkeypatch.setattr(inference, "stage1", lambda image: _observations())
    yield
    inference._CACHE.clear()
    inference.COST_LOG.clear()


def test_successful_identical_photo_reuses_cache_and_records_savings(monkeypatch):
    provider_calls = 0

    def vlm(image, declared_type, claimed_complete=False):
        nonlocal provider_calls
        provider_calls += 1
        return {
            "label": "door", "completion": "complete", "reason": "Door leaf is visible.",
            "model": inference.VLM_MODEL,
            "_metering": {"calls": [_call(inference.VLM_MODEL)],
                          "fallback_reasons": [], "valid_response": True},
        }

    monkeypatch.setattr(inference, "stage2_vlm", vlm)
    first = inference.analyze(_image_bytes(), "E-1", "door")
    second = inference.analyze(_image_bytes(), "E-2", "door")

    assert provider_calls == 1
    assert not first.get("cache_hit")
    assert second["cache_hit"] is True
    assert second["evidence_id"] == "E-2"
    assert inference.COST_LOG[0]["models_called"] == [inference.STAGE1_MODEL, inference.VLM_MODEL]
    assert inference.COST_LOG[0]["siglip_latency_s"] >= 0
    assert inference.COST_LOG[0]["vlm_latency_s"] == pytest.approx(.2)
    assert inference.COST_LOG[0]["input_tokens"] == 12
    assert inference.COST_LOG[1]["models_called"] == []
    assert inference.COST_LOG[1]["models_reused"] == [inference.STAGE1_MODEL, inference.VLM_MODEL]
    assert inference.COST_LOG[1]["avoided_provider_cost_usd"] == pytest.approx(.001)
    summary = inference.cost_summary()
    assert summary["photos_processed"] == 2
    assert summary["cache_hits"] == 1
    assert summary["est_total_cost_usd"] == pytest.approx(.001)
    assert summary["avoided_provider_cost_usd"] == pytest.approx(.001)
    assert {"photos_processed", "escalation_rate", "avg_latency_s", "est_total_cost_usd",
            "est_cost_if_always_vlm_usd", "cache_hits", "log"} <= set(summary)
    assert {"estimated_cost_usd", "provider_confirmed_cost_usd", "total_cost_usd",
            "estimated_savings_vs_always_vlm_usd"} <= set(summary)


def test_incomplete_vlm_response_is_never_cached(monkeypatch):
    attempts = 0

    def incomplete(image, declared_type, claimed_complete=False):
        nonlocal attempts
        attempts += 1
        return {
            "label": "other", "completion": "unclear", "reason": "unparsed text",
            "model": inference.VLM_MODEL,
            "_metering": {"calls": [_call(inference.VLM_MODEL)],
                          "fallback_reasons": [], "valid_response": False},
        }

    monkeypatch.setattr(inference, "stage2_vlm", incomplete)
    for evidence_id in ("I-1", "I-2"):
        result = inference.analyze(_image_bytes(), evidence_id, "door")
        assert not result.get("cache_hit")
    assert attempts == 2
    assert not inference._CACHE
    assert all(not row["successful"] for row in inference.COST_LOG)


def test_failed_analysis_is_metered_and_never_cached(monkeypatch):
    attempts = 0

    def failure(image, declared_type, claimed_complete=False):
        nonlocal attempts
        attempts += 1
        calls = [_call(inference.VLM_MODEL, error="provider down",
                       input_tokens=None, output_tokens=None)]
        raise inference.VLMCallError("all VLMs failed", calls, [f"{inference.VLM_MODEL}:RuntimeError"])

    monkeypatch.setattr(inference, "stage2_vlm", failure)
    for evidence_id in ("F-1", "F-2"):
        result = inference.analyze(_image_bytes(), evidence_id, "door")
        assert result["vlm_error"] == "all VLMs failed"
    assert attempts == 2
    assert not inference._CACHE
    assert all(row["input_tokens"] is None for row in inference.COST_LOG)
    assert all(row["fallback_reasons"] for row in inference.COST_LOG)


def test_fallback_and_confirmed_costs_remain_distinct(monkeypatch):
    primary = _call(inference.VLM_MODEL, cost=.002, error="primary failed",
                    input_tokens=None, output_tokens=None)
    fallback = _call(inference.VLM_FALLBACK, confirmed=.0005,
                     input_tokens=20, output_tokens=4)

    def vlm(image, declared_type, claimed_complete=False):
        return {
            "label": "door", "completion": "partial", "reason": "Frame only.",
            "model": inference.VLM_FALLBACK,
            "_metering": {"calls": [primary, fallback],
                          "fallback_reasons": [f"{inference.VLM_MODEL}:RuntimeError"],
                          "valid_response": True},
        }

    monkeypatch.setattr(inference, "stage2_vlm", vlm)
    inference.analyze(_image_bytes(), "M-1", "door")
    record = inference.COST_LOG[0]
    assert record["models_called"] == [inference.STAGE1_MODEL, inference.VLM_MODEL, inference.VLM_FALLBACK]
    assert record["estimated_cost_usd"] == pytest.approx(.002)
    assert record["provider_confirmed_cost_usd"] == pytest.approx(.0005)
    assert record["total_cost_usd"] == pytest.approx(.0025)
    assert record["cost_source"] == "mixed"
    assert record["input_tokens"] is None  # never infer the missing primary usage
    assert record["fallback_reasons"] == [f"{inference.VLM_MODEL}:RuntimeError"]
