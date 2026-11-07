"""Regression guards for the saved A1 prompt comparison; no live models/providers."""
import csv
import json
import os
from pathlib import Path

# These must be set before importing any AI module, independent of pytest order.
os.environ["SITEWISE_DISABLE_MODELS"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

from ai import inference
from ai.evaluate_prompt_regression import PREVIOUS_PROMPTS


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "a1_prompt_regression"


def _csv(name):
    with (OUTPUT / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_saved_prompt_comparison_and_minimal_change_are_reproducible():
    summary = json.loads((OUTPUT / "summary.json").read_text(encoding="utf-8"))
    assert summary["held_out_a7_used"] is False
    assert summary["provider_calls"] == 0
    assert summary["label_order"] == list(inference.LABELS)
    assert len(summary["input_sha256"]) == 37
    assert all(not name.startswith("test/") for name in summary["input_sha256"])

    by_name = {row["prompt_set"]: row for row in summary["summary"]}
    assert by_name["captain_current"]["correct"] == 34
    assert by_name["captain_current"]["errors"] == ["other (9).jpg", "wall (2).jpg", "wall.jpg"]
    assert by_name["previous_descriptive"]["correct"] == 37
    assert by_name["minimal_wall_other"]["correct"] == 37

    current = summary["prompts"]["captain_current"]
    minimal = summary["prompts"]["minimal_wall_other"]
    assert {label for label in current if current[label] != minimal[label]} == {"wall", "other"}
    assert minimal["wall"] == PREVIOUS_PROMPTS["wall"]
    assert minimal["other"] == PREVIOUS_PROMPTS["other"]
    assert len(_csv("results.csv")) == 3 * 37
    assert summary["repeats"] == 3
    assert all(row["mean_inference_latency_s"] > 0 for row in summary["summary"])
    assert all(row["median_inference_latency_s"] > 0 for row in summary["summary"])


def test_error_ablations_identify_the_exact_single_prompt_fixes():
    rows = _csv("error_ablations.csv")
    single_fixes = {
        row["filename"]: sorted(candidate["swapped_prompts"] for candidate in rows
                                if candidate["filename"] == row["filename"]
                                and candidate["fixed"] == "True" and candidate["swap_count"] == "1")
        for row in rows
    }
    assert single_fixes == {
        "other (9).jpg": ["other"],
        "wall (2).jpg": ["other", "wall"],
        "wall.jpg": ["wall"],
    }
