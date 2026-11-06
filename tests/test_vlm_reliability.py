"""A2 VLM validation/fallback tests; providers are always mocked."""
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

# Set before importing any AI module, regardless of pytest collection order.
os.environ["SITEWISE_DISABLE_MODELS"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

from ai import inference


def _response(content, *, finish_reason="stop", usage=None):
    choice = SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice], usage=usage)


def _valid(label="door", completion="partial", reason="Visible door frame remains unfinished."):
    return json.dumps({"label": label, "completion": completion, "reason": reason})


class FakeClient:
    def __init__(self, actions):
        self.actions = actions
        self.models_called = []

    def chat_completion(self, *, model, **kwargs):
        self.models_called.append(model)
        action = self.actions[model]
        if isinstance(action, BaseException):
            raise action
        return action


def _install_client(monkeypatch, actions):
    import huggingface_hub

    client = FakeClient(actions)
    monkeypatch.setattr(huggingface_hub, "InferenceClient", lambda token=None: client)
    return client


def _image():
    return Image.new("RGB", (32, 32), (80, 100, 120))


def test_valid_markdown_gemma_stops_before_qwen(monkeypatch):
    client = _install_client(monkeypatch, {
        inference.VLM_MODEL: _response(f"```json\n{_valid()}\n```"),
        inference.VLM_FALLBACK: AssertionError("Qwen must not be called"),
    })
    result = inference.stage2_vlm(_image(), "door")
    assert result["label"] == "door"
    assert result["model"] == inference.VLM_MODEL
    assert client.models_called == [inference.VLM_MODEL]
    assert result["_metering"]["fallback_reasons"] == []


def test_invalid_gemma_json_falls_back_to_valid_qwen_surrounded_text(monkeypatch):
    client = _install_client(monkeypatch, {
        inference.VLM_MODEL: _response("not JSON"),
        inference.VLM_FALLBACK: _response(f"Result follows: {_valid('wall', 'complete', 'Blocks are visible.')} done"),
    })
    result = inference.stage2_vlm(_image(), "wall")
    assert result["label"] == "wall"
    assert result["model"] == inference.VLM_FALLBACK
    assert client.models_called == [inference.VLM_MODEL, inference.VLM_FALLBACK]
    assert "no valid JSON object" in result["_metering"]["calls"][0]["error"]


def test_truncated_gemma_response_calls_qwen(monkeypatch):
    client = _install_client(monkeypatch, {
        inference.VLM_MODEL: _response('{"label":"door"', finish_reason="length"),
        inference.VLM_FALLBACK: _response(_valid()),
    })
    result = inference.stage2_vlm(_image(), "door")
    assert result["model"] == inference.VLM_FALLBACK
    assert client.models_called == [inference.VLM_MODEL, inference.VLM_FALLBACK]
    assert "truncated" in result["_metering"]["calls"][0]["error"]


def test_missing_fields_from_both_models_is_a_metered_failure(monkeypatch):
    client = _install_client(monkeypatch, {
        inference.VLM_MODEL: _response('{"label":"door","completion":"partial"}'),
        inference.VLM_FALLBACK: _response('{"label":"door","reason":"Visible frame."}'),
    })
    with pytest.raises(inference.VLMCallError) as caught:
        inference.stage2_vlm(_image(), "door")
    assert client.models_called == [inference.VLM_MODEL, inference.VLM_FALLBACK]
    assert len(caught.value.calls) == 2
    assert "missing reason" in caught.value.calls[0]["error"]
    assert "missing completion" in caught.value.calls[1]["error"]


@pytest.mark.parametrize("bad_payload", [
    '{"label":"window","completion":"complete","reason":"Visible."}',
    '{"label":"door","completion":"finished","reason":"Visible."}',
    '{"label":"door","completion":"partial","reason":"   "}',
])
def test_invalid_gemma_schema_values_call_qwen(monkeypatch, bad_payload):
    client = _install_client(monkeypatch, {
        inference.VLM_MODEL: _response(bad_payload),
        inference.VLM_FALLBACK: _response(_valid()),
    })
    result = inference.stage2_vlm(_image(), "door")
    assert result["model"] == inference.VLM_FALLBACK
    assert client.models_called == [inference.VLM_MODEL, inference.VLM_FALLBACK]


def test_timeout_uses_qwen_and_unclear_is_acceptable(monkeypatch):
    client = _install_client(monkeypatch, {
        inference.VLM_MODEL: TimeoutError("Gemma timed out"),
        inference.VLM_FALLBACK: _response(_valid("other", "unclear", "The view is obstructed.")),
    })
    result = inference.stage2_vlm(_image(), None)
    assert result["completion"] == "unclear"
    assert result["model"] == inference.VLM_FALLBACK
    assert client.models_called == [inference.VLM_MODEL, inference.VLM_FALLBACK]
    assert "TimeoutError" in result["_metering"]["fallback_reasons"][0]


def test_valid_uncertain_gemma_does_not_call_qwen(monkeypatch):
    client = _install_client(monkeypatch, {
        inference.VLM_MODEL: _response(_valid("other", "unclear", "Evidence is insufficient.")),
        inference.VLM_FALLBACK: AssertionError("Qwen must not be called"),
    })
    result = inference.stage2_vlm(_image(), None)
    assert result["completion"] == "unclear"
    assert client.models_called == [inference.VLM_MODEL]


@pytest.fixture
def analyze_setup(monkeypatch):
    inference._CACHE.clear()
    inference.COST_LOG.clear()
    monkeypatch.setattr(inference, "DISABLED", False)
    monkeypatch.setattr(inference, "stage1", lambda image: [
        {"label": "door", "score": .4}, {"label": "wall", "score": .3},
        {"label": "ceiling", "score": .2}, {"label": "other", "score": .1},
    ])
    output = io.BytesIO()
    _image().save(output, format="JPEG")
    yield output.getvalue()
    inference._CACHE.clear()
    inference.COST_LOG.clear()


def test_total_vlm_failure_never_certifies_or_enters_success_cache(monkeypatch, analyze_setup):
    calls = [{
        "model": inference.VLM_MODEL, "latency_s": .1, "input_tokens": None,
        "output_tokens": None, "estimated_cost_usd": inference.VLM_COST,
        "provider_reported_cost_usd": None, "provider_confirmed_cost_usd": None,
        "cost_source": "estimated", "error": "timeout",
    }]
    monkeypatch.setattr(inference, "stage2_vlm", lambda *args, **kwargs: (_ for _ in ()).throw(
        inference.VLMCallError("all VLMs failed", calls, ["Gemma:TimeoutError"])))
    result = inference.analyze(analyze_setup, "FAIL-1", "door")
    assert result["requires_review"] is True
    assert result["completion_certified"] is False
    assert result["completion"] is None
    assert result["vlm_error"] == "all VLMs failed"
    assert not inference._CACHE


def test_complete_vlm_observation_still_never_certifies(monkeypatch, analyze_setup):
    monkeypatch.setattr(inference, "stage2_vlm", lambda *args, **kwargs: {
        "label": "door", "completion": "complete", "reason": "Door leaf and hardware are visible.",
        "model": inference.VLM_MODEL,
        "_metering": {"calls": [], "fallback_reasons": [], "valid_response": True},
    })
    result = inference.analyze(analyze_setup, "OK-1", "door", claimed_complete=True)
    assert result["completion"] == "complete"
    assert result["requires_review"] is True
    assert result["completion_certified"] is False


def test_env_example_matches_captain_models():
    values = {}
    for line in (Path(__file__).resolve().parents[1] / ".env.example").read_text().splitlines():
        if line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value
    assert values["SITEWISE_STAGE1_MODEL"] == "google/siglip2-base-patch16-224"
    assert values["SITEWISE_VLM_MODEL"] == "google/gemma-4-31B-it"
    assert values["SITEWISE_VLM_FALLBACK"] == "Qwen/Qwen2.5-VL-72B-Instruct"
    assert values["SITEWISE_ESCALATION_THRESHOLD"] == "0.80"
