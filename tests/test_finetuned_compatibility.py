"""A6 fine-tuned path and embedding compatibility guards; no live models/providers."""
import io
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

os.environ["SITEWISE_DISABLE_MODELS"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

from ai import inference


MODEL = "mfjbrr/team-QH045-sitewise"
ROOT = Path(__file__).resolve().parents[1]


def test_finetuned_environment_selects_image_classification_pipeline(monkeypatch):
    calls = []

    class FakePipe:
        def __call__(self, image, top_k):
            assert top_k == 4
            return [
                {"label": "door", "score": .7}, {"label": "wall", "score": .1},
                {"label": "ceiling", "score": .1}, {"label": "other", "score": .1},
            ]

    def fake_pipeline(task, model):
        calls.append((task, model))
        return FakePipe()

    monkeypatch.setattr(inference, "FINETUNED_MODEL", MODEL)
    monkeypatch.setattr(inference, "_pipe", None)
    monkeypatch.setitem(sys.modules, "transformers", SimpleNamespace(pipeline=fake_pipeline))
    kind, _ = inference._stage1_pipe()
    observations = inference.stage1(object())
    assert kind == "ft"
    assert calls == [("image-classification", MODEL)]
    assert {row["label"] for row in observations} == {"door", "wall", "ceiling", "other"}
    assert sum(row["score"] for row in observations) == pytest.approx(1.0)


def test_embedding_accepts_transformers_pooled_output_wrapper(monkeypatch):
    import torch

    class FakeModel:
        def get_image_features(self, **inputs):
            return SimpleNamespace(pooler_output=torch.tensor([[3.0, 4.0]]))

    class FakeProcessor:
        def __call__(self, **kwargs):
            return {"pixel_values": torch.zeros((1, 3, 2, 2))}

    output = io.BytesIO()
    Image.new("RGB", (4, 4), "blue").save(output, format="PNG")
    monkeypatch.setattr(inference, "DISABLED", False)
    monkeypatch.setattr(inference, "_embedder", lambda: (FakeModel(), FakeProcessor()))
    assert inference.embed(output.getvalue()) == [0.6, 0.8]


def test_saved_real_a6_result_matches_acceptance_criteria():
    summary = json.loads((ROOT / "data" / "a6_finetuned_compatibility" / "summary.json")
                         .read_text(encoding="utf-8"))
    assert summary["model"] == MODEL
    assert summary["pipeline_kind"] == "ft"
    assert set(summary["checkpoint_label2id"]) == {"door", "wall", "ceiling", "other"}
    assert summary["fine_tuned"]["accuracy"] > summary["zero_shot_existing_baseline"]["accuracy"]
    assert summary["analyze_checks"]["category_mismatch"]["model_id"] == MODEL
    assert summary["analyze_checks"]["category_mismatch"]["escalation_reason"] == "label_mismatch"
    assert summary["analyze_checks"]["low_confidence"]["escalation_reason"] == "low_confidence"
    assert summary["analyze_checks"]["provider_calls"] == 0
    assert summary["analyze_checks"]["cache_hit"] is True
    assert summary["duplicate_check"]["kind"] == "exact"
    for route in ("category_mismatch", "low_confidence"):
        assert summary["analyze_checks"][route]["requires_review"] is True
        assert summary["analyze_checks"][route]["completion_certified"] is False
