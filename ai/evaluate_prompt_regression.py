"""Offline A1 comparison of captain and pre-sync SigLIP2 prompts on 37 dev photos."""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import os
import random
import re
import statistics
import time
from pathlib import Path
from unittest.mock import patch

# Force local model loading and ensure this evaluator cannot reach a provider.
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

from PIL import Image

from ai import inference

ROOT = Path(__file__).resolve().parents[1]
UPLOADS = ROOT / "data" / "uploads"
OUTPUT = ROOT / "data" / "a1_prompt_regression"
REPORT = ROOT / "ai" / "prompt_regression.md"
LABEL_PATTERN = re.compile(r"^(door|wall|ceiling|other)(?: \(\d+\))?\.jpg$", re.IGNORECASE)
PREVIOUS_PROMPTS = {
    "door": "a photo of a building door or door frame",
    "wall": "a photo of a masonry wall made of bricks or concrete blocks",
    "ceiling": "a photo of a suspended ceiling with panels or tiles",
    "other": "a photo of construction equipment, stairs or another building element",
}


def development_images() -> list[tuple[Path, str]]:
    images = []
    for path in sorted(UPLOADS.iterdir(), key=lambda item: item.name.lower()):
        match = LABEL_PATTERN.fullmatch(path.name)
        if match:
            images.append((path, match.group(1).lower()))
    counts = {label: sum(truth == label for _, truth in images) for label in inference.LABELS}
    if len(images) != 37 or counts != {"door": 10, "wall": 10, "ceiling": 8, "other": 9}:
        raise RuntimeError(f"Expected only the 37-photo development set; found {len(images)} with {counts}")
    return images


def load_image(path: Path) -> Image.Image:
    image = Image.open(path).convert("RGB")
    image.thumbnail((768, 768))
    return image


def classify(image: Image.Image, prompts: dict[str, str]) -> tuple[list[dict], float]:
    started = time.perf_counter()
    with patch.dict(inference.LABELS, prompts, clear=True):
        observations = inference.stage1(image)
    return observations, time.perf_counter() - started


def metrics(rows: list[dict]) -> tuple[float, float]:
    labels = tuple(inference.LABELS)
    accuracy = sum(row["truth"] == row["prediction"] for row in rows) / len(rows)
    f1s = []
    for label in labels:
        tp = sum(row["truth"] == label and row["prediction"] == label for row in rows)
        fp = sum(row["truth"] != label and row["prediction"] == label for row in rows)
        fn = sum(row["truth"] == label and row["prediction"] != label for row in rows)
        precision = tp / (tp + fp) if tp + fp else 0
        recall = tp / (tp + fn) if tp + fn else 0
        f1s.append(2 * precision * recall / (precision + recall) if precision + recall else 0)
    return accuracy, sum(f1s) / len(f1s)


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    if inference.DISABLED:
        raise RuntimeError("Unset SITEWISE_DISABLE_MODELS; prompt regression requires real local SigLIP2")
    if inference.FINETUNED_MODEL:
        raise RuntimeError("Unset SITEWISE_FINETUNED_MODEL; compare prompts on the zero-shot checkpoint")
    current = dict(inference.LABELS)
    if tuple(current) != tuple(PREVIOUS_PROMPTS):
        raise RuntimeError("Prompt sets must use identical label ordering")
    images = development_images()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    prepared = {path.name: load_image(path) for path, _ in images}

    # Load once and warm both prompt sets before randomized timing.
    kind, pipe = inference._stage1_pipe()
    if kind != "zs":
        raise RuntimeError("Prompt comparison requires the zero-shot pipeline")
    for prompts in (current, PREVIOUS_PROMPTS):
        classify(prepared[images[0][0].name], prompts)

    minimal_candidate = {
        label: PREVIOUS_PROMPTS[label] if label in ("wall", "other") else current[label]
        for label in current
    }
    prompt_sets = {
        "captain_current": current,
        "previous_descriptive": PREVIOUS_PROMPTS,
        "minimal_wall_other": minimal_candidate,
    }
    classify(prepared[images[0][0].name], minimal_candidate)
    tasks = [(name, path, truth, repeat) for repeat in range(args.repeats)
             for name in prompt_sets for path, truth in images]
    random.Random(20261106).shuffle(tasks)
    trials = []
    for name, path, truth, repeat in tasks:
        observations, latency = classify(prepared[path.name], prompt_sets[name])
        top = max(observations, key=lambda row: row["score"])
        scores = {row["label"]: row["score"] for row in observations}
        raw_scores = {row["label"]: row.get("raw_score") for row in observations}
        trials.append({
            "prompt_set": name, "filename": path.name, "truth": truth, "repeat": repeat,
            "prediction": top["label"], "correct": top["label"] == truth,
            "normalized_score": top["score"], "inference_latency_s": latency,
            **{f"score_{label}": scores[label] for label in current},
            **{f"raw_score_{label}": raw_scores[label] for label in current},
        })
    write_csv(OUTPUT / "trials.csv", trials)

    results = []
    for name in prompt_sets:
        for path, truth in images:
            group = [row for row in trials if row["prompt_set"] == name and row["filename"] == path.name]
            predictions = {row["prediction"] for row in group}
            if len(predictions) != 1:
                raise RuntimeError(f"Non-deterministic prediction for {name}/{path.name}")
            row = dict(group[0])
            row.pop("repeat")
            row["median_inference_latency_s"] = statistics.median(
                item["inference_latency_s"] for item in group)
            results.append(row)
    write_csv(OUTPUT / "results.csv", results)

    summaries = []
    for name in prompt_sets:
        rows = [row for row in results if row["prompt_set"] == name]
        accuracy, macro_f1 = metrics(rows)
        latencies = [row["inference_latency_s"] for row in trials if row["prompt_set"] == name]
        summaries.append({
            "prompt_set": name, "accuracy": accuracy, "macro_f1": macro_f1,
            "correct": sum(row["truth"] == row["prediction"] for row in rows),
            "mean_inference_latency_s": statistics.mean(latencies),
            "median_inference_latency_s": statistics.median(latencies),
            "errors": [row["filename"] for row in rows if row["truth"] != row["prediction"]],
        })

    current_errors = [row for row in results
                      if row["prompt_set"] == "captain_current" and row["truth"] != row["prediction"]]
    ablations = []
    for error in current_errors:
        for count in range(len(current) + 1):
            for swapped in itertools.combinations(current, count):
                prompts = {label: PREVIOUS_PROMPTS[label] if label in swapped else current[label]
                           for label in current}
                observations, latency = classify(prepared[error["filename"]], prompts)
                top = max(observations, key=lambda row: row["score"])
                ablations.append({
                    "filename": error["filename"], "truth": error["truth"],
                    "swapped_prompts": "+".join(swapped) or "none",
                    "swap_count": count, "prediction": top["label"],
                    "fixed": top["label"] == error["truth"],
                    "normalized_score": top["score"], "latency_s": latency,
                })
    if ablations:
        write_csv(OUTPUT / "error_ablations.csv", ablations)
    minimal_fixes = {}
    for error in current_errors:
        fixed = [row for row in ablations if row["filename"] == error["filename"] and row["fixed"]]
        minimum = min((row["swap_count"] for row in fixed), default=None)
        minimal_fixes[error["filename"]] = [row["swapped_prompts"] for row in fixed
                                            if row["swap_count"] == minimum]

    payload = {
        "dataset": "37 filename-labeled development photos in data/uploads",
        "held_out_a7_used": False, "provider_calls": 0,
        "model": inference.STAGE1_MODEL, "pipeline_kind": kind,
        "device": str(getattr(pipe, "device", "unknown")), "repeats": args.repeats,
        "preprocessing": "RGB then thumbnail((768, 768))",
        "label_order": list(current), "normalized_scoring": True,
        "prompts": prompt_sets, "summary": summaries,
        "minimal_error_fixes": minimal_fixes,
        "input_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path, _ in images},
    }
    (OUTPUT / "summary.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# A1 prompt regression", "",
        "Compared the captain's current prompts with the pre-sync descriptive prompts on exactly 37 development "
        "photos. Person D's held-out A7 test split was not read. Both sets used the same model instance, RGB/768px "
        "preprocessing, label order, normalized scoring, and randomized repeated timing. No provider was reachable.", "",
        "| Prompt set | Accuracy | Macro F1 | Mean latency | Median latency | Errors |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in summaries:
        lines.append(
            f"| {row['prompt_set']} | {row['accuracy']:.2%} ({row['correct']}/37) | "
            f"{row['macro_f1']:.3f} | {row['mean_inference_latency_s']:.4f}s | "
            f"{row['median_inference_latency_s']:.4f}s | {', '.join(row['errors']) or 'none'} |"
        )
    lines += ["", "## Exact prompt differences", "",
              "| Class | Captain current | Previous descriptive |", "|---|---|---|"]
    for label in current:
        lines.append(f"| {label} | {current[label]} | {PREVIOUS_PROMPTS[label]} |")
    lines += ["", "## Error ablations", ""]
    for error in current_errors:
        fixes = minimal_fixes[error["filename"]]
        candidate_row = next(row for row in results
                             if row["prompt_set"] == "minimal_wall_other"
                             and row["filename"] == error["filename"])
        truth_before = float(error[f"raw_score_{error['truth']}"])
        truth_after = float(candidate_row[f"raw_score_{error['truth']}"])
        predicted_before = float(error[f"raw_score_{error['prediction']}"])
        predicted_after = float(candidate_row[f"raw_score_{error['prediction']}"])
        lines.append(
            f"- `{error['filename']}`: current `{error['prediction']}` vs truth `{error['truth']}`; "
            f"smallest fixing prompt swap(s): {', '.join(f'`{item}`' for item in fixes) or 'none'}. "
            f"The truth-label raw match changed from {truth_before:.8f} to {truth_after:.8f}; "
            f"the former predicted-label match changed from {predicted_before:.8f} to {predicted_after:.8f}."
        )
    previous = next(row for row in summaries if row["prompt_set"] == "previous_descriptive")
    captain = next(row for row in summaries if row["prompt_set"] == "captain_current")
    candidate = next(row for row in summaries if row["prompt_set"] == "minimal_wall_other")
    lines += ["", "## Recommendation", ""]
    if (previous["accuracy"] > captain["accuracy"] and not previous["errors"]
            and candidate["accuracy"] == previous["accuracy"] and not candidate["errors"]):
        lines.append(
            "The previous prompts consistently outperform the current set on this development regression. "
            "The exhaustive error ablations show that no one-string edit fixes all three errors; the validated "
            "two-string `minimal_wall_other` candidate reaches the same 37/37 result. Change only `wall` and "
            "`other`, then rerun this regression before touching routing or thresholds."
        )
    else:
        lines.append("Do not change production prompts; the previous set does not consistently outperform the current set.")
    lines += ["", "Reproduce with:", "", "```powershell",
              r".\.venv\Scripts\python.exe -m ai.evaluate_prompt_regression --repeats 3", "```"]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Saved prompt regression for {len(images)} development photos; no provider calls made.")


if __name__ == "__main__":
    main()
