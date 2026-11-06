"""Evaluate normalized SigLIP2 escalation thresholds on development photos only."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import time
from pathlib import Path

from PIL import Image

from ai import inference

ROOT = Path(__file__).resolve().parents[1]
UPLOADS = ROOT / "data" / "uploads"
OUTPUT = ROOT / "data" / "a3_threshold_evaluation"
PREDICTIONS = OUTPUT / "development_predictions.csv"
DETAILS = OUTPUT / "threshold_details.csv"
SUMMARY = OUTPUT / "summary.json"
REPORT = ROOT / "ai" / "threshold_results.md"
CLASSES = tuple(inference.LABELS)
THRESHOLDS = tuple(round(value / 100, 2) for value in range(50, 100, 5))
LABEL_PATTERN = re.compile(r"^(door|wall|ceiling|other)(?: \(\d+\))?\.jpg$", re.IGNORECASE)


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def development_images() -> list[tuple[Path, str]]:
    images = []
    for path in sorted(UPLOADS.iterdir(), key=lambda item: item.name.lower()):
        match = LABEL_PATTERN.fullmatch(path.name)
        if match:
            images.append((path, match.group(1).lower()))
    counts = {label: sum(truth == label for _, truth in images) for label in CLASSES}
    if len(images) != 37 or counts != {"door": 10, "wall": 10, "ceiling": 8, "other": 9}:
        raise RuntimeError(f"Expected the 37-photo development set; found {len(images)} with {counts}")
    return images


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def predict(refresh: bool) -> list[dict]:
    images = development_images()
    cached = {row["filename"]: row for row in read_csv(PREDICTIONS)}
    rows = []
    for path, truth in images:
        digest = sha256(path)
        row = cached.get(path.name)
        if (not refresh and row and row.get("sha256") == digest
                and row.get("model") == inference.STAGE1_MODEL
                and row.get("score_type") == "normalized"):
            rows.append(row)
            continue
        started = time.perf_counter()
        with Image.open(path) as opened:
            observations = inference.stage1(opened.convert("RGB"))
        latency = time.perf_counter() - started
        scores = {item["label"]: float(item["score"]) for item in observations}
        if set(scores) != set(CLASSES) or abs(sum(scores.values()) - 1.0) > 1e-5:
            raise RuntimeError(f"Stage 1 did not return four normalized scores for {path.name}")
        top = max(observations, key=lambda item: item["score"])
        rows.append({
            "filename": path.name, "sha256": digest, "truth": truth,
            "prediction": top["label"], "score": float(top["score"]),
            "score_type": "normalized", "model": inference.STAGE1_MODEL,
            "latency_s": latency,
            **{f"score_{label}": scores[label] for label in CLASSES},
        })
    write_csv(PREDICTIONS, rows, [
        "filename", "sha256", "truth", "prediction", "score", "score_type", "model", "latency_s",
        *(f"score_{label}" for label in CLASSES),
    ])
    return rows


def classification_metrics(rows: list[dict]) -> tuple[float, float]:
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


def measured_gemma_cost() -> tuple[float, str]:
    rows = read_csv(ROOT / "data" / "a7_evaluation" / "provider_calls.csv")
    costs = [float(row["cost_usd"]) for row in rows
             if row.get("model") == inference.VLM_MODEL and not row.get("error") and row.get("cost_usd")]
    if not costs:
        return inference.VLM_COST, "configured fallback estimate; no measured A7 usage found"
    sources = sorted({row.get("cost_source", "unknown") for row in rows
                      if row.get("model") == inference.VLM_MODEL and not row.get("error")})
    return sum(costs) / len(costs), "A7 mean from measured tokens; " + ", ".join(sources)


def evaluate(rows: list[dict]) -> tuple[list[dict], list[dict], dict]:
    accuracy, macro_f1 = classification_metrics(rows)
    gemma_cost, cost_source = measured_gemma_cost()
    results, details = [], []
    for threshold in THRESHOLDS:
        low_only, mismatch_only, both, escalated, escaped = [], [], [], [], []
        for row in rows:
            low = float(row["score"]) < threshold
            mismatch = row["prediction"] != row["truth"]
            reason = "low_confidence_and_mismatch" if low and mismatch else (
                "low_confidence" if low else "declared_category_mismatch" if mismatch else "")
            if reason:
                escalated.append(row["filename"])
                if low and mismatch:
                    both.append(row["filename"])
                elif low:
                    low_only.append(row["filename"])
                else:
                    mismatch_only.append(row["filename"])
            if mismatch and not reason:
                escaped.append(row["filename"])
            details.append({
                "threshold": threshold, "filename": row["filename"], "truth": row["truth"],
                "prediction": row["prediction"], "normalized_score": row["score"],
                "escalated": bool(reason), "escalation_reason": reason,
                "incorrect_avoids_escalation": mismatch and not bool(reason),
            })
        results.append({
            "threshold": threshold,
            "siglip_accuracy": accuracy,
            "siglip_macro_f1": macro_f1,
            "measured_cascade_accuracy": None,
            "measured_cascade_macro_f1": None,
            "escalated": len(escalated), "escalation_pct": 100 * len(escalated) / len(rows),
            "low_confidence_only": low_only, "declared_mismatch_only": mismatch_only,
            "low_confidence_and_mismatch": both,
            "incorrect_avoids_escalation": escaped,
            "estimated_provider_cost_per_photo_usd": len(escalated) * gemma_cost / len(rows),
        })
    summary = {
        "dataset": "37 filename-labeled development photos in data/uploads",
        "held_out_test_split_used": False,
        "score_type": "normalized SigLIP2 class share",
        "model": inference.STAGE1_MODEL,
        "photos": len(rows), "accuracy": accuracy, "macro_f1": macro_f1,
        "gemma_cost_per_escalation_usd": gemma_cost, "cost_source": cost_source,
        "current_gemma_responses_for_development_photos": 0,
        "results": results,
    }
    return results, details, summary


def markdown(results: list[dict], summary: dict) -> str:
    lines = [
        "# A3: normalized SigLIP2 escalation threshold evaluation", "",
        "## Method", "",
        "Thresholds were selected on the 37 existing filename-labeled development photos in `data/uploads/`. "
        "Person D's 32-image held-out test split was not read or used. Predictions are real outputs from the "
        "captain's current `inference.stage1`; `score` is the normalized four-class share and `raw_score` is not used.", "",
        f"Provider cost uses **${summary['gemma_cost_per_escalation_usd']:.8f} per escalation** "
        f"({summary['cost_source']}). There are no saved current-Gemma responses for these 37 photos, so "
        "post-escalation cascade accuracy is **not measured**. No fallback labels are mocked or inferred.", "",
        "| Threshold | SigLIP accuracy | Macro F1 | Escalated | Est. cost/photo | Low only | Mismatch only | Both | Incorrect not escalated |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in results:
        lines.append(
            f"| {row['threshold']:.2f} | {row['siglip_accuracy']:.2%} | {row['siglip_macro_f1']:.3f} | "
            f"{row['escalated']}/{summary['photos']} ({row['escalation_pct']:.2f}%) | "
            f"${row['estimated_provider_cost_per_photo_usd']:.8f} | {len(row['low_confidence_only'])} | "
            f"{len(row['declared_mismatch_only'])} | {len(row['low_confidence_and_mismatch'])} | "
            f"{len(row['incorrect_avoids_escalation'])} |"
        )
    lines += ["", "## Escalated photos by threshold", ""]
    for row in results:
        def names(key: str) -> str:
            return ", ".join(f"`{name}`" for name in row[key]) or "none"
        lines += [
            f"### {row['threshold']:.2f}", "",
            f"- Low confidence only: {names('low_confidence_only')}",
            f"- Declared-category mismatch only: {names('declared_mismatch_only')}",
            f"- Both reasons: {names('low_confidence_and_mismatch')}",
            f"- Incorrect predictions avoiding escalation: {names('incorrect_avoids_escalation')}", "",
        ]
    minimum_rate = min(row["escalation_pct"] for row in results)
    minimum = max((row for row in results if row["escalation_pct"] == minimum_rate),
                  key=lambda row: row["threshold"])
    lines += [
        "## Recommendation", "",
        f"Thresholds 0.50–0.60 tie for the lowest escalation rate and cost. **{minimum['threshold']:.2f}** is "
        f"the efficient provisional choice at the top of that plateau: {minimum['escalation_pct']:.2f}% "
        f"escalation and ${minimum['estimated_provider_cost_per_photo_usd']:.8f}/photo, with no additional calls "
        "versus 0.50. The declared-category mismatch rule "
        "still routes every observed SigLIP error, so no incorrect development prediction avoids escalation.", "",
        "It is **not yet safe to adopt as a production default**. The development set is small, the declared label "
        "makes mismatch routing unusually informative, and current-Gemma post-escalation accuracy is unavailable "
        "for these photos. Validate the frozen candidate once on Person D's untouched held-out split and retain "
        "human review before changing the live threshold.", "",
        "## Reproduce", "", "```powershell",
        r".\.venv\Scripts\python.exe -m ai.evaluate_thresholds --refresh", "```", "",
        "`development_predictions.csv` caches image SHA-256 values and normalized model outputs; "
        "`threshold_details.csv` records the routing reason for every photo and threshold.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="rerun local SigLIP2 instead of valid cached rows")
    args = parser.parse_args()
    rows = predict(args.refresh)
    results, details, summary = evaluate(rows)
    write_csv(DETAILS, details, [
        "threshold", "filename", "truth", "prediction", "normalized_score", "escalated",
        "escalation_reason", "incorrect_avoids_escalation",
    ])
    SUMMARY.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    REPORT.write_text(markdown(results, summary), encoding="utf-8")
    print(f"Saved {len(results)} thresholds for {len(rows)} development photos; no provider calls made.")


if __name__ == "__main__":
    main()
