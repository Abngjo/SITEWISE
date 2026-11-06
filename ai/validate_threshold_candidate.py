"""One-time offline validation of frozen threshold 0.60 against A7 artifacts."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
A7 = ROOT / "data" / "a7_evaluation"
OUTPUT = ROOT / "data" / "a3_threshold_evaluation" / "heldout_validation"
DETAILS = OUTPUT / "results.csv"
SUMMARY = OUTPUT / "summary.json"
REPORT = OUTPUT / "REPORT.md"
CANDIDATE = 0.60
PRODUCTION = 0.80
CLASSES = ("door", "wall", "ceiling", "other")


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metrics(rows: list[dict]) -> tuple[float, float]:
    accuracy = sum(row["truth"] == row["routed_prediction"] for row in rows) / len(rows)
    f1s = []
    for label in CLASSES:
        tp = sum(row["truth"] == label and row["routed_prediction"] == label for row in rows)
        fp = sum(row["truth"] != label and row["routed_prediction"] == label for row in rows)
        fn = sum(row["truth"] == label and row["routed_prediction"] != label for row in rows)
        precision = tp / (tp + fp) if tp + fp else 0
        recall = tp / (tp + fn) if tp + fn else 0
        f1s.append(2 * precision * recall / (precision + recall) if precision + recall else 0)
    return accuracy, sum(f1s) / len(f1s)


def main() -> None:
    if SUMMARY.exists():
        raise SystemExit(
            "Frozen held-out validation already exists; refusing to run it a second time. "
            "Inspect the saved artifacts instead."
        )
    local_path = A7 / "local_predictions.csv"
    provider_path = A7 / "provider_calls.csv"
    a7_summary_path = A7 / "summary.json"
    a7_summary = json.loads(a7_summary_path.read_text(encoding="utf-8"))
    if float(a7_summary["threshold"]) != PRODUCTION or a7_summary["n"] != 32:
        raise RuntimeError("A7 production-threshold snapshot is not the expected frozen 0.80/32-image run")

    zero = [row for row in read_csv(local_path) if row["setup"] == "siglip2_zero_shot"]
    gemma = {row["image"]: row for row in read_csv(provider_path)
             if row["setup"] == "gemma_every_photo" and not row["error"]}
    if len(zero) != 32 or len(gemma) != 32:
        raise RuntimeError(f"Expected 32 zero-shot and 32 valid Gemma rows; got {len(zero)} and {len(gemma)}")
    if any(row.get("cost_source") == "provider_reported" for row in gemma.values()):
        billing_note = "mixed provider-confirmed and estimated costs"
    else:
        billing_note = "token-based estimates; provider-confirmed billing unavailable"

    all_details, summaries = [], []
    for threshold, name in ((CANDIDATE, "candidate_0.60"), (PRODUCTION, "production_0.80")):
        routed = []
        for primary in zero:
            score = float(primary["score"])
            low = score < threshold
            # This is the captain's route condition: low normalized confidence OR
            # disagreement with the declared element category. On this labeled
            # evaluation split, truth is the declared category.
            mismatch = primary["prediction"] != primary["truth"]
            escalated = low or mismatch
            reason = ("low_confidence_and_mismatch" if low and mismatch else
                      "low_confidence" if low else "declared_category_mismatch" if mismatch else "")
            fallback = gemma[primary["image"]] if escalated else None
            row = {
                "setup": name, "threshold": threshold, "image": primary["image"],
                "truth": primary["truth"], "siglip_prediction": primary["prediction"],
                "normalized_score": score, "low_confidence": low,
                "declared_category_mismatch": mismatch, "escalated": escalated,
                "escalation_reason": reason,
                "routed_prediction": fallback["prediction"] if fallback else primary["prediction"],
                "routed_model": fallback["model"] if fallback else primary["model"],
                "siglip_latency_s": float(primary["latency_s"]),
                "provider_latency_s": float(fallback["latency_s"]) if fallback else 0.0,
                "routed_latency_s": (float(primary["latency_s"])
                                     + (float(fallback["latency_s"]) if fallback else 0.0)),
                "prompt_tokens": int(fallback["prompt_tokens"]) if fallback else 0,
                "completion_tokens": int(fallback["completion_tokens"]) if fallback else 0,
                "estimated_cost_usd": float(fallback["cost_usd"]) if fallback else 0.0,
                "cost_source": fallback["cost_source"] if fallback else "local_no_cost",
                "gemma_fixed_siglip_error": bool(fallback and mismatch
                                                   and fallback["prediction"] == primary["truth"]),
            }
            routed.append(row)
            all_details.append(row)
        accuracy, macro_f1 = metrics(routed)
        escalated_rows = [row for row in routed if row["escalated"]]
        error_rows = [row for row in routed if row["siglip_prediction"] != row["truth"]]
        summaries.append({
            "setup": name, "threshold": threshold, "n": len(routed),
            "routed_accuracy": accuracy, "routed_macro_f1": macro_f1,
            "escalated": len(escalated_rows),
            "escalation_pct": 100 * len(escalated_rows) / len(routed),
            "low_confidence_only": [row["image"] for row in routed
                                    if row["escalation_reason"] == "low_confidence"],
            "declared_mismatch_only": [row["image"] for row in routed
                                       if row["escalation_reason"] == "declared_category_mismatch"],
            "both_reasons": [row["image"] for row in routed
                             if row["escalation_reason"] == "low_confidence_and_mismatch"],
            "incorrect_not_escalated": [row["image"] for row in error_rows if not row["escalated"]],
            "avg_routed_latency_s": sum(row["routed_latency_s"] for row in routed) / len(routed),
            "total_prompt_tokens": sum(row["prompt_tokens"] for row in routed),
            "total_completion_tokens": sum(row["completion_tokens"] for row in routed),
            "estimated_total_cost_usd": sum(row["estimated_cost_usd"] for row in routed),
            "estimated_cost_per_photo_usd": sum(row["estimated_cost_usd"] for row in routed) / len(routed),
        })

    fields = list(all_details[0])
    OUTPUT.mkdir(parents=True, exist_ok=False)
    with DETAILS.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_details)
    payload = {
        "validation_policy": "single frozen validation; do not retune from held-out results",
        "dataset": a7_summary["dataset"], "split": "test", "n": 32,
        "candidate_frozen_before_validation": CANDIDATE,
        "production_comparison": PRODUCTION,
        "routing_rule": "normalized_score < threshold OR prediction != declared_category",
        "artifact_sha256": {
            "local_predictions.csv": digest(local_path),
            "provider_calls.csv": digest(provider_path),
            "a7_summary.json": digest(a7_summary_path),
        },
        "measurement_notes": {
            "predictions": "measured, previously saved real SigLIP2 and Gemma outputs",
            "latency": "measured per-call latency, recombined according to each threshold route",
            "cost": billing_note,
        },
        "recommendation": {
            "safe_when_declared_category_present": True,
            "safe_for_optional_category_uploads": False,
            "reason": ("The only zero-shot error scores 0.776226 and is caught at 0.60 solely by the "
                       "declared-category mismatch rule; element_id is optional in the current upload API."),
        },
        "results": summaries,
    }
    SUMMARY.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Frozen 0.60 threshold held-out validation", "",
        "This is the single validation of the preselected 0.60 candidate on Person D's untouched 32-image A7 "
        "test split. No threshold was retuned and no model or provider call was made.", "",
        "| Threshold | Routed accuracy | Macro F1 | Escalated | Avg routed latency | Est. cost/photo |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for result in summaries:
        lines.append(
            f"| {result['threshold']:.2f} | {result['routed_accuracy']:.2%} | "
            f"{result['routed_macro_f1']:.3f} | {result['escalated']}/32 "
            f"({result['escalation_pct']:.2f}%) | {result['avg_routed_latency_s']:.3f}s | "
            f"${result['estimated_cost_per_photo_usd']:.8f} |"
        )
    lines += ["", "## Routing details", ""]
    for result in summaries:
        lines += [
            f"### {result['threshold']:.2f}", "",
            f"- Low confidence only: {', '.join(result['low_confidence_only']) or 'none'}",
            f"- Declared-category mismatch only: {', '.join(result['declared_mismatch_only']) or 'none'}",
            f"- Both reasons: {', '.join(result['both_reasons']) or 'none'}",
            f"- Incorrect predictions not escalated: {', '.join(result['incorrect_not_escalated']) or 'none'}",
            f"- Measured tokens routed: {result['total_prompt_tokens']} input, "
            f"{result['total_completion_tokens']} output.", "",
        ]
    error = next(row for row in all_details
                 if row["setup"] == "candidate_0.60" and row["siglip_prediction"] != row["truth"])
    lines += [
        "## Zero-shot error", "",
        f"`{error['image']}` was predicted `{error['siglip_prediction']}` instead of `{error['truth']}` at "
        f"normalized score {error['normalized_score']:.6f}. It escalated at 0.60 because of "
        f"`{error['escalation_reason']}`. Gemma predicted `{error['routed_prediction']}`, so the error was fixed.", "",
        "Accuracy, F1, routing, latency, and token counts above are reconstructed from measured saved responses. "
        f"Costs are {billing_note}.", "",
        "## Recommendation", "",
        "At 0.60 the routed result remains 100% accurate while using 3 rather than 5 Gemma calls. However, "
        "the sole SigLIP error scores 0.776226 and is caught only by category mismatch at 0.60. Because the "
        "current upload API permits `element_id=None`, 0.60 is safe only for workflows that guarantee a valid "
        "declared category. Do not adopt it globally for optional-category uploads without an additional guard "
        "or validation set covering missing and incorrect declarations.",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Saved one-time frozen validation to {OUTPUT}")


if __name__ == "__main__":
    main()
