"""Offline A6 verification of Person D's fine-tuned SigLIP2 checkpoint."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import statistics
import time
from pathlib import Path
from unittest.mock import patch

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ.setdefault("SITEWISE_FINETUNED_MODEL", "mfjbrr/team-QH045-sitewise")

from PIL import Image

from ai import duplicates, inference

ROOT = Path(__file__).resolve().parents[1]
MODEL = "mfjbrr/team-QH045-sitewise"
UPLOADS = ROOT / "data" / "uploads"
OUTPUT = ROOT / "data" / "a6_finetuned_compatibility"
REPORT = ROOT / "ai" / "finetuned_compatibility.md"
CLASSES = ("door", "wall", "ceiling", "other")
PATTERN = re.compile(r"^(door|wall|ceiling|other)(?: \(\d+\))?\.jpg$", re.IGNORECASE)


def images() -> list[tuple[Path, str]]:
    result = []
    for path in sorted(UPLOADS.iterdir(), key=lambda item: item.name.lower()):
        match = PATTERN.fullmatch(path.name)
        if match:
            result.append((path, match.group(1).lower()))
    if len(result) != 37:
        raise RuntimeError(f"Expected 37 development photos, found {len(result)}")
    return result


def metrics(rows: list[dict]) -> tuple[float, float]:
    accuracy = sum(row["truth"] == row["prediction"] for row in rows) / len(rows)
    f1s = []
    for label in CLASSES:
        tp = sum(row["truth"] == label and row["prediction"] == label for row in rows)
        fp = sum(row["truth"] != label and row["prediction"] == label for row in rows)
        fn = sum(row["truth"] == label and row["prediction"] != label for row in rows)
        precision = tp / (tp + fp) if tp + fp else 0
        recall = tp / (tp + fn) if tp + fn else 0
        f1s.append(2 * precision * recall / (precision + recall) if precision + recall else 0)
    return accuracy, sum(f1s) / len(f1s)


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    if inference.DISABLED:
        raise RuntimeError("Unset SITEWISE_DISABLE_MODELS; A6 requires real local stage-one inference")
    if inference.FINETUNED_MODEL != MODEL:
        raise RuntimeError(f"Expected SITEWISE_FINETUNED_MODEL={MODEL}, got {inference.FINETUNED_MODEL!r}")
    dataset = images()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    kind, pipe = inference._stage1_pipe()
    if kind != "ft":
        raise RuntimeError(f"Expected fine-tuned pipeline kind, got {kind!r}")

    config = pipe.model.config
    id2label = {int(key): str(value).lower() for key, value in config.id2label.items()}
    label2id = {str(key).lower(): int(value) for key, value in config.label2id.items()}
    if set(id2label.values()) != set(CLASSES) or set(label2id) != set(CLASSES):
        raise RuntimeError(f"Checkpoint labels are incompatible: id2label={id2label}, label2id={label2id}")

    first = Image.open(dataset[0][0]).convert("RGB")
    first.thumbnail((768, 768))
    inference.stage1(first)  # warm-up excluded from latency
    trials = []
    repeats = 3
    for repeat in range(repeats):
        for path, truth in dataset:
            with Image.open(path) as opened:
                image = opened.convert("RGB")
            image.thumbnail((768, 768))
            started = time.perf_counter()
            observations = inference.stage1(image)
            latency = time.perf_counter() - started
            labels = {row["label"] for row in observations}
            score_sum = sum(float(row["score"]) for row in observations)
            if labels != set(CLASSES) or abs(score_sum - 1.0) > 1e-5:
                raise RuntimeError(f"Invalid normalized labels/scores for {path.name}: {observations}")
            top = max(observations, key=lambda row: row["score"])
            trials.append({
                "filename": path.name, "truth": truth, "repeat": repeat,
                "prediction": top["label"], "score": float(top["score"]),
                "latency_s": latency, "model_id": inference.FINETUNED_MODEL,
                **{f"score_{row['label']}": float(row["score"]) for row in observations},
            })
    write_csv(OUTPUT / "trials.csv", trials)
    predictions = []
    for path, truth in dataset:
        group = [row for row in trials if row["filename"] == path.name]
        if len({row["prediction"] for row in group}) != 1:
            raise RuntimeError(f"Non-deterministic fine-tuned label for {path.name}")
        row = dict(group[0])
        row.pop("repeat")
        row["median_latency_s"] = statistics.median(item["latency_s"] for item in group)
        predictions.append(row)
    write_csv(OUTPUT / "predictions.csv", predictions)
    fine_accuracy, fine_f1 = metrics(predictions)

    baseline = [row for row in read_csv(ROOT / "data" / "a1_prompt_regression" / "results.csv")
                if row["prompt_set"] == "captain_current"]
    zero_accuracy, zero_f1 = metrics(baseline)
    zero_latency = statistics.mean(float(row["median_inference_latency_s"]) for row in baseline)

    development_minimum = min(predictions, key=lambda row: float(row["score"]))
    low = development_minimum
    low_path = UPLOADS / low["filename"]
    low_source = "development"
    if float(low["score"]) >= inference.THRESHOLD:
        # The development set contains no sub-0.80 score. Reuse the already
        # evaluated A7 minimum solely as a routing compatibility case; do not
        # select or change a threshold from it.
        from huggingface_hub import snapshot_download

        a7_rows = [row for row in read_csv(ROOT / "data" / "a7_evaluation" / "local_predictions.csv")
                   if row["setup"] == "siglip2_finetuned"]
        saved_low = min(a7_rows, key=lambda row: float(row["score"]))
        folder = Path(snapshot_download(
            "mfjbrr/team-QH045-sitewise-photos", repo_type="dataset",
            allow_patterns=[saved_low["image"]], local_files_only=True,
        ))
        low_path = folder / saved_low["image"]
        with Image.open(low_path) as opened:
            low_image = opened.convert("RGB")
        low_image.thumbnail((768, 768))
        low_observations = inference.stage1(low_image)
        low_top = max(low_observations, key=lambda row: row["score"])
        low = {
            "filename": saved_low["image"], "truth": saved_low["truth"],
            "prediction": low_top["label"], "score": float(low_top["score"]),
        }
        low_source = "previously evaluated A7 held-out example (routing check only)"
        if float(low["score"]) >= inference.THRESHOLD:
            raise RuntimeError(f"Expected a real low-confidence case, got {low}")
    representative = next(row for row in predictions if row["truth"] == "door")
    mismatch_declared = next(label for label in CLASSES if label != representative["prediction"])
    provider_stub_calls = []

    def offline_vlm(image, declared_type, claimed_complete=False):
        provider_stub_calls.append({"declared_type": declared_type, "claimed_complete": claimed_complete})
        return {
            "label": declared_type or "other", "completion": "unclear",
            "reason": "Offline A6 routing stub; no provider called.", "model": inference.VLM_MODEL,
            "_metering": {
                "calls": [{
                    "model": inference.VLM_MODEL, "latency_s": 0.0,
                    "input_tokens": None, "output_tokens": None,
                    "estimated_cost_usd": 0.0, "provider_reported_cost_usd": None,
                    "provider_confirmed_cost_usd": None, "cost_source": "offline_mock", "error": None,
                }],
                "fallback_reasons": [], "valid_response": True,
            },
        }

    def bytes_for(filename: str) -> bytes:
        return (UPLOADS / filename).read_bytes()

    inference._CACHE.clear()
    inference.COST_LOG.clear()
    with patch.object(inference, "stage2_vlm", offline_vlm):
        mismatch_result = inference.analyze(
            bytes_for(representative["filename"]), "A6-MISMATCH", mismatch_declared)
        low_result = inference.analyze(low_path.read_bytes(), "A6-LOW", low["truth"])
        cached_result = inference.analyze(low_path.read_bytes(), "A6-CACHE", low["truth"])
    if len(provider_stub_calls) != 2 or not cached_result.get("cache_hit"):
        raise RuntimeError("Expected one mismatch route, one low-confidence route, and one cache hit")
    for result in (mismatch_result, low_result, cached_result):
        if result["model_id"] != MODEL or not result["requires_review"] or result["completion_certified"]:
            raise RuntimeError(f"Fine-tuned analyze contract mismatch: {result}")

    # Embeddings deliberately remain tied to the base SigLIP2 encoder; verify
    # fine-tuned classification configuration does not break duplicate checks.
    sample_bytes = bytes_for(representative["filename"])
    embedding = inference.embed(sample_bytes)
    if not embedding:
        raise RuntimeError("SigLIP2 duplicate embedding unavailable under fine-tuned configuration")
    digest = hashlib.sha256(sample_bytes).hexdigest()
    phash = duplicates.phash_bytes(sample_bytes)
    original = {"evidence_id": "DUP-1", "sha256": digest, "phash": phash,
                "embedding": embedding, "certificate_no": "A6"}
    clone = dict(original, evidence_id="DUP-2")
    duplicate_matches = duplicates.find_duplicates(clone, [original])
    if not duplicate_matches or duplicate_matches[0]["kind"] != "exact":
        raise RuntimeError("Duplicate detection changed under fine-tuned configuration")

    cost_summary = inference.cost_summary()
    if cost_summary["photos_processed"] != 3 or cost_summary["cache_hits"] != 1:
        raise RuntimeError(f"Cost/cache accounting mismatch: {cost_summary}")
    routing_records = [row for row in inference.COST_LOG if not row["cache_hit"]]
    if any(row["models_called"][0] != MODEL for row in routing_records):
        raise RuntimeError("Cost log does not identify the fine-tuned stage-one model")

    summary = {
        "model": MODEL, "pipeline_kind": kind, "device": str(getattr(pipe, "device", "unknown")),
        "checkpoint_id2label": id2label, "checkpoint_label2id": label2id,
        "development_photos": len(predictions), "repeats": repeats,
        "fine_tuned": {
            "accuracy": fine_accuracy, "macro_f1": fine_f1,
            "mean_latency_s": statistics.mean(float(row["latency_s"]) for row in trials),
            "median_latency_s": statistics.median(float(row["latency_s"]) for row in trials),
            "errors": [row["filename"] for row in predictions if row["truth"] != row["prediction"]],
        },
        "zero_shot_existing_baseline": {
            "accuracy": zero_accuracy, "macro_f1": zero_f1, "mean_latency_s": zero_latency,
            "errors": [row["filename"] for row in baseline if row["truth"] != row["prediction"]],
        },
        "production_threshold_unchanged": inference.THRESHOLD,
        "fine_tuned_escalation_at_0.80": {
            "count": sum(float(row["score"]) < inference.THRESHOLD
                         or row["prediction"] != row["truth"] for row in predictions),
            "development_minimum": development_minimum,
            "low_confidence_case": low, "low_confidence_case_source": low_source,
        },
        "analyze_checks": {
            "category_mismatch": {k: mismatch_result.get(k) for k in (
                "model_id", "escalation_model_id", "final_label", "escalation_reason",
                "requires_review", "completion_certified")},
            "low_confidence": {k: low_result.get(k) for k in (
                "model_id", "escalation_model_id", "final_label", "escalation_reason",
                "requires_review", "completion_certified")},
            "cache_hit": cached_result.get("cache_hit"),
            "provider_calls": 0, "offline_vlm_stub_calls": len(provider_stub_calls),
        },
        "cost_summary": {key: value for key, value in cost_summary.items() if key != "log"},
        "duplicate_check": duplicate_matches[0],
        "routing_models": {"primary": inference.VLM_MODEL, "fallback": inference.VLM_FALLBACK},
    }
    (OUTPUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# A6 fine-tuned SigLIP2 compatibility", "",
        f"Checkpoint: `{MODEL}`. Real local stage-one inference; provider calls disabled.", "",
        "| Stage-one setup | Accuracy | Macro F1 | Mean latency | Errors |",
        "|---|---:|---:|---:|---|",
        f"| Captain zero-shot baseline | {zero_accuracy:.2%} | {zero_f1:.3f} | {zero_latency:.4f}s | "
        f"{', '.join(summary['zero_shot_existing_baseline']['errors']) or 'none'} |",
        f"| Person D fine-tuned | {fine_accuracy:.2%} | {fine_f1:.3f} | "
        f"{summary['fine_tuned']['mean_latency_s']:.4f}s | {', '.join(summary['fine_tuned']['errors']) or 'none'} |",
        "", "## Compatibility checks", "",
        f"- Pipeline kind: `{kind}`; device: `{summary['device']}`; model_id: `{MODEL}`.",
        f"- Labels: `{', '.join(CLASSES)}` with normalized scores summing to one.",
        f"- Production threshold remains {inference.THRESHOLD:.2f}; "
        f"{summary['fine_tuned_escalation_at_0.80']['count']}/37 development photos would escalate.",
        f"- Real low-confidence case: `{low['filename']}` at {float(low['score']):.6f} "
        f"from {low_source}; routed via offline VLM stub.",
        f"- Category mismatch case: `{representative['filename']}` declared `{mismatch_declared}`; routed via offline VLM stub.",
        "- Repeating the low-confidence photo produced a SHA-256 inference cache hit with no second VLM stub call.",
        f"- Duplicate detection remained compatible (`{duplicate_matches[0]['kind']}`); embedding length {len(embedding)}.",
        "- Cost logs identify the fine-tuned repo as the stage-one model; review/certification flags remain safe.",
        f"- Existing provider order remains `{inference.VLM_MODEL}` then `{inference.VLM_FALLBACK}`.",
        "", "No production environment setting, threshold, routing model, contract, or API response shape was changed.",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Saved A6 compatibility results for {len(predictions)} photos; no provider calls made.")


if __name__ == "__main__":
    main()
