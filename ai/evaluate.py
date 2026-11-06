"""A6/A7 evaluation for the captain's current SITEWISE model cascade.

Local phase (free):
    python -m ai.evaluate --local

Provider phase (potentially billable, requires explicit approval):
    python -m ai.evaluate --remote --approved-paid-calls \
        --gemma-cost-per-call USD --qwen-cost-per-call USD

The held-out test split is never used to tune prompts, weights, or thresholds.
Provider calls are checkpointed by image/model and are never retried automatically.
"""
from __future__ import annotations

import argparse
import base64
import csv
import io
import json
import os
import time
from pathlib import Path

from huggingface_hub import InferenceClient, get_token, snapshot_download
from PIL import Image

from ai import inference


ROOT = Path(__file__).resolve().parents[1]
DATASET_ID = "mfjbrr/team-QH045-sitewise-photos"
FINETUNED_MODEL = "mfjbrr/team-QH045-sitewise"
GEMMA_INPUT_USD_PER_MILLION = 0.27
GEMMA_OUTPUT_USD_PER_MILLION = 0.76
CLASSES = ("door", "wall", "ceiling", "other")
OUTPUT = ROOT / "data" / "a7_evaluation"
LOCAL_ROWS = OUTPUT / "local_predictions.csv"
PROVIDER_ROWS = OUTPUT / "provider_calls.csv"
RESULT_ROWS = OUTPUT / "results.csv"
SUMMARY_JSON = OUTPUT / "summary.json"
REPORT_MD = OUTPUT / "REPORT.md"


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    atomic_write(path, stream.getvalue())


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def test_images() -> list[tuple[Path, str, str]]:
    folder = Path(snapshot_download(
        DATASET_ID, repo_type="dataset", allow_patterns=["test/**", "README.md", "sources.csv"]
    ))
    rows = []
    for path in sorted((folder / "test").glob("*/*")):
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            label = path.parent.name
            if label not in CLASSES:
                raise RuntimeError(f"Unexpected test label: {label}")
            rows.append((path, label, path.relative_to(folder).as_posix()))
    counts = {label: sum(truth == label for _, truth, _ in rows) for label in CLASSES}
    if len(rows) != 32 or set(counts.values()) != {8}:
        raise RuntimeError(f"Expected 32 held-out images, 8 per class; found {counts}")
    return rows


def _device() -> int:
    import torch
    return 0 if torch.cuda.is_available() else -1


def run_local() -> None:
    from transformers import pipeline

    images = test_images()
    device = _device()
    zero_kind, zero_pipe = inference._stage1_pipe()
    if zero_kind != "zs" or inference.FINETUNED_MODEL:
        raise RuntimeError("Local zero-shot evaluation requires SITEWISE_FINETUNED_MODEL to be unset")
    fine_pipe = pipeline("image-classification", model=FINETUNED_MODEL, device=device)

    # Warm both local pipelines before timing. Model construction/download is excluded.
    warm = Image.open(images[0][0]).convert("RGB")
    inference.stage1(warm)
    fine_pipe(warm, top_k=len(CLASSES))

    rows = []
    for path, truth, relative in images:
        image = Image.open(path).convert("RGB")
        started = time.perf_counter()
        zero_scores = inference.stage1(image)
        zero_latency = time.perf_counter() - started
        zero_top = max(zero_scores, key=lambda row: row["score"])
        rows.append({
            "setup": "siglip2_zero_shot", "image": relative, "truth": truth,
            "prediction": zero_top["label"], "score": zero_top["score"],
            "raw_score": zero_top.get("raw_score", ""), "latency_s": zero_latency,
            "model": inference.STAGE1_MODEL,
        })

        started = time.perf_counter()
        fine_scores = fine_pipe(image, top_k=len(CLASSES))
        fine_latency = time.perf_counter() - started
        fine_top = max(fine_scores, key=lambda row: float(row["score"]))
        if fine_top["label"] not in CLASSES:
            raise RuntimeError(f"Fine-tuned model returned unexpected label {fine_top['label']!r}")
        rows.append({
            "setup": "siglip2_finetuned", "image": relative, "truth": truth,
            "prediction": fine_top["label"], "score": float(fine_top["score"]),
            "raw_score": "", "latency_s": fine_latency, "model": FINETUNED_MODEL,
        })

    write_csv(LOCAL_ROWS, rows, [
        "setup", "image", "truth", "prediction", "score", "raw_score", "latency_s", "model"
    ])
    build_reports(gemma_cost_per_call=0.0, qwen_cost_per_call=0.0)
    print(f"Saved {len(rows)} local predictions to {LOCAL_ROWS}. No provider calls made.")


def _prompt(declared_type: str) -> str:
    # Kept byte-for-byte equivalent to the captain's claimed_complete=False prompt.
    return (
        "You are assisting a construction site engineer. Look at the photo and answer ONLY with JSON: "
        '{"label": one of ["door","wall","ceiling","other"], '
        '"completion": one of ["complete","partial","not_started","unclear"], '
        '"reason": "<one short sentence>"}. '
        f"The contractor says this photo shows a {declared_type}."
    )


def _read_usage(usage, key):
    return usage.get(key) if isinstance(usage, dict) else getattr(usage, key, None)


def _call_once(client, path: Path, truth: str, model: str, setup: str,
               estimated_cost: float) -> dict:
    raw = path.read_bytes()
    with Image.open(io.BytesIO(raw)) as source:
        buf = io.BytesIO()
        source.convert("RGB").save(buf, format="JPEG", quality=85)
    url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    started = time.perf_counter()
    try:
        response = client.chat_completion(
            model=model,
            messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": url}},
                {"type": "text", "text": _prompt(truth)},
            ]}],
            max_tokens=300,
        )
        latency = time.perf_counter() - started
        if not response.choices or not response.choices[0].message.content:
            raise ValueError("provider returned no message content")
        text = response.choices[0].message.content
        try:
            parsed = json.loads(text[text.find("{"): text.rfind("}") + 1])
        except Exception:
            parsed = {"label": "other", "completion": "unclear", "reason": text[:200]}
        usage = getattr(response, "usage", None)
        prompt_tokens = _read_usage(usage, "prompt_tokens") if usage is not None else None
        completion_tokens = _read_usage(usage, "completion_tokens") if usage is not None else None
        provider_cost = _read_usage(usage, "estimated_cost") if usage is not None else None
        cost = float(provider_cost) if type(provider_cost) in (int, float) else estimated_cost
        return {
            "setup": setup, "image": path.name, "truth": truth, "model": model,
            "prediction": parsed.get("label", ""), "completion": parsed.get("completion", ""),
            "reason": parsed.get("reason", ""), "latency_s": latency,
            "prompt_tokens": prompt_tokens if type(prompt_tokens) is int else "",
            "completion_tokens": completion_tokens if type(completion_tokens) is int else "",
            "cost_usd": cost, "cost_source": "provider_reported" if type(provider_cost) in (int, float) else "estimated",
            "error": "",
        }
    except Exception as exc:
        return {
            "setup": setup, "image": path.name, "truth": truth, "model": model,
            "prediction": "", "completion": "", "reason": "",
            "latency_s": time.perf_counter() - started, "prompt_tokens": "",
            "completion_tokens": "", "cost_usd": estimated_cost,
            "cost_source": "estimated_failed_attempt", "error": str(exc),
        }


def run_remote(gemma_cost_per_call: float, qwen_cost_per_call: float) -> None:
    if not LOCAL_ROWS.exists():
        raise RuntimeError("Run --local successfully before provider evaluation")
    token = os.getenv("HF_TOKEN") or get_token()
    if not token:
        raise RuntimeError("HF authentication is required; no requests were sent")
    images = test_images()
    local = {(row["setup"], row["image"]): row for row in read_csv(LOCAL_ROWS)}
    existing = read_csv(PROVIDER_ROWS)
    seen = {(row["setup"], row["image"], row["model"]) for row in existing}
    client = InferenceClient(token=token)

    # One Gemma call per test photo. Cascade reuses the identical Gemma response
    # for its escalated subset instead of paying for duplicate requests.
    for path, truth, relative in images:
        key = ("gemma_every_photo", relative, inference.VLM_MODEL)
        if key in seen:
            continue
        row = _call_once(client, path, truth, inference.VLM_MODEL,
                         "gemma_every_photo", gemma_cost_per_call)
        row["image"] = relative
        existing.append(row)
        seen.add(key)
        write_csv(PROVIDER_ROWS, existing, list(row))

    gemma = {(row["image"]): row for row in existing
             if row["setup"] == "gemma_every_photo" and row["model"] == inference.VLM_MODEL}
    for path, truth, relative in images:
        zero = local[("siglip2_zero_shot", relative)]
        escalate = (float(zero["score"]) < inference.THRESHOLD or zero["prediction"] != truth)
        gemma_row = gemma.get(relative)
        if not escalate or (gemma_row and not gemma_row["error"]):
            continue
        key = ("cascade_fallback", relative, inference.VLM_FALLBACK)
        if key in seen:
            continue
        row = _call_once(client, path, truth, inference.VLM_FALLBACK,
                         "cascade_fallback", qwen_cost_per_call)
        row["image"] = relative
        existing.append(row)
        seen.add(key)
        write_csv(PROVIDER_ROWS, existing, list(row))

    build_reports(gemma_cost_per_call, qwen_cost_per_call)
    print(f"Provider phase complete. Calls are checkpointed in {PROVIDER_ROWS}; no automatic retries.")


def classification_metrics(rows: list[dict]) -> tuple[float | None, float | None]:
    valid = [row for row in rows if row["prediction"] in CLASSES]
    if not valid:
        return None, None
    accuracy = sum(row["prediction"] == row["truth"] for row in valid) / len(valid)
    f1s = []
    for label in CLASSES:
        tp = sum(row["prediction"] == label and row["truth"] == label for row in valid)
        fp = sum(row["prediction"] == label and row["truth"] != label for row in valid)
        fn = sum(row["prediction"] != label and row["truth"] == label for row in valid)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    return accuracy, sum(f1s) / len(f1s)


def build_reports(gemma_cost_per_call: float, qwen_cost_per_call: float) -> None:
    local = read_csv(LOCAL_ROWS)
    providers = read_csv(PROVIDER_ROWS)
    if not local:
        return
    # Hugging Face currently returns token counts for these calls but not a billed
    # amount. Replace the deliberately conservative pre-call ceiling with a
    # token-based estimate while preserving its provenance in the checkpoint.
    repriced = False
    for row in providers:
        if (row.get("model") == inference.VLM_MODEL
                and row.get("cost_source") == "estimated"
                and str(row.get("prompt_tokens", "")).isdigit()
                and str(row.get("completion_tokens", "")).isdigit()):
            row["cost_usd"] = (
                int(row["prompt_tokens"]) * GEMMA_INPUT_USD_PER_MILLION
                + int(row["completion_tokens"]) * GEMMA_OUTPUT_USD_PER_MILLION
            ) / 1_000_000
            row["cost_source"] = "calculated_from_provider_tokens"
            repriced = True
    if repriced:
        write_csv(PROVIDER_ROWS, providers, [
            "setup", "image", "truth", "model", "prediction", "completion", "reason",
            "latency_s", "prompt_tokens", "completion_tokens", "cost_usd", "cost_source", "error"
        ])
    by_local = {name: [row for row in local if row["setup"] == name]
                for name in ("siglip2_zero_shot", "siglip2_finetuned")}
    gemma = {row["image"]: row for row in providers
             if row["setup"] == "gemma_every_photo" and row["model"] == inference.VLM_MODEL}
    qwen = {row["image"]: row for row in providers
            if row["setup"] == "cascade_fallback" and row["model"] == inference.VLM_FALLBACK}

    result_rows = []
    for row in local:
        result_rows.append({
            "setup": row["setup"], "image": row["image"], "truth": row["truth"],
            "prediction": row["prediction"], "correct": row["truth"] == row["prediction"],
            "latency_s": row["latency_s"], "cost_usd": 0.0, "escalated": False,
            "model": row["model"], "error": "",
        })
    for zero in by_local["siglip2_zero_shot"]:
        remote = gemma.get(zero["image"])
        if remote:
            result_rows.append({
                "setup": "gemma_every_photo", "image": zero["image"], "truth": zero["truth"],
                "prediction": remote["prediction"], "correct": remote["prediction"] == zero["truth"],
                "latency_s": remote["latency_s"], "cost_usd": remote["cost_usd"], "escalated": True,
                "model": remote["model"], "error": remote["error"],
            })
        escalate = float(zero["score"]) < inference.THRESHOLD or zero["prediction"] != zero["truth"]
        prediction, model, error, remote_latency, remote_cost = zero["prediction"], zero["model"], "", 0.0, 0.0
        if escalate:
            chosen = remote
            if chosen and chosen["error"]:
                chosen = qwen.get(zero["image"])
            if chosen:
                prediction, model, error = chosen["prediction"], chosen["model"], chosen["error"]
                remote_latency, remote_cost = float(chosen["latency_s"]), float(chosen["cost_usd"])
            else:
                prediction, error = "", "missing provider result"
        result_rows.append({
            "setup": "sitewise_cascade", "image": zero["image"], "truth": zero["truth"],
            "prediction": prediction, "correct": prediction == zero["truth"],
            "latency_s": float(zero["latency_s"]) + remote_latency, "cost_usd": remote_cost,
            "escalated": escalate, "model": model, "error": error,
        })
    write_csv(RESULT_ROWS, result_rows, [
        "setup", "image", "truth", "prediction", "correct", "latency_s", "cost_usd",
        "escalated", "model", "error"
    ])

    names = ("siglip2_zero_shot", "siglip2_finetuned", "gemma_every_photo", "sitewise_cascade")
    summary = []
    for name in names:
        rows = [row for row in result_rows if row["setup"] == name]
        evaluated = sum(row["prediction"] in CLASSES for row in rows)
        remote_dependent = name in ("gemma_every_photo", "sitewise_cascade")
        complete = len(rows) == 32 and evaluated == 32 and not any(row["error"] for row in rows)
        accuracy, macro_f1 = classification_metrics(rows)
        if remote_dependent and not complete:
            accuracy = macro_f1 = None
        avg_latency = sum(float(row["latency_s"]) for row in rows) / len(rows) if rows else None
        avg_cost = sum(float(row["cost_usd"]) for row in rows) / len(rows) if rows else None
        if remote_dependent and not complete:
            avg_latency = avg_cost = None
        escalation_pct = (100.0 if name == "gemma_every_photo" else
                          100 * sum(str(row["escalated"]).lower() == "true" for row in rows) / len(rows)
                          if rows else None)
        summary.append({
            "setup": name, "n": 32, "evaluated": evaluated,
            "accuracy": accuracy, "macro_f1": macro_f1,
            "avg_latency_s": avg_latency, "estimated_cost_per_photo_usd": avg_cost,
            "escalation_pct": escalation_pct,
            "errors": sum(bool(row["error"]) for row in rows),
        })
    payload = {
        "dataset": DATASET_ID, "split": "test", "n": 32,
        "threshold": inference.THRESHOLD, "threshold_tuned_on_test": False,
        "zero_shot_model": inference.STAGE1_MODEL, "finetuned_model": FINETUNED_MODEL,
        "gemma_model": inference.VLM_MODEL, "fallback_model": inference.VLM_FALLBACK,
        "gemma_token_rates_usd_per_million": {
            "input": GEMMA_INPUT_USD_PER_MILLION,
            "output": GEMMA_OUTPUT_USD_PER_MILLION,
        },
        "gemma_cost_per_call_fallback": gemma_cost_per_call,
        "qwen_cost_per_call_fallback": qwen_cost_per_call,
        "summary": summary,
    }
    atomic_write(SUMMARY_JSON, json.dumps(payload, indent=2) + "\n")
    lines = [
        "# SITEWISE A6/A7 held-out evaluation", "",
        f"Dataset: `{DATASET_ID}`, fixed `test` split, n=32 (8 images per class). "
        "The test split was not used to tune prompts, thresholds, or model weights.", "",
        "| Setup | Accuracy | Macro F1 | Avg latency | Est. cost/photo | Escalation | Evaluated |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary:
        pct = lambda value: "pending" if value is None else f"{100*value:.2f}%"
        number = lambda value, digits=3: "pending" if value is None else f"{value:.{digits}f}"
        escalation = "pending" if row["escalation_pct"] is None else f"{row['escalation_pct']:.2f}%"
        lines.append(
            f"| {row['setup']} | {pct(row['accuracy'])} | {number(row['macro_f1'])} | "
            f"{number(row['avg_latency_s'])} s | "
            f"{'pending' if row['estimated_cost_per_photo_usd'] is None else '$'+format(row['estimated_cost_per_photo_usd'], '.8f')} | "
            f"{escalation} | {row['evaluated']}/{row['n']} |"
        )
    lines += [
        "", "Local model construction/download time is excluded; per-image preprocessing and inference are included. "
        "Provider latency and token counts come from real calls. The provider did not return billed amounts, so costs are "
        "calculated estimates from measured tokens and published rates. Provider calls are checkpointed and never retried automatically.",
    ]
    if providers:
        gemma_calls = [row for row in providers if row.get("model") == inference.VLM_MODEL]
        qwen_calls = [row for row in providers if row.get("model") == inference.VLM_FALLBACK]
        prompt_tokens = sum(int(row["prompt_tokens"]) for row in providers
                            if str(row.get("prompt_tokens", "")).isdigit())
        completion_tokens = sum(int(row["completion_tokens"]) for row in providers
                                if str(row.get("completion_tokens", "")).isdigit())
        total_cost = sum(float(row.get("cost_usd") or 0) for row in providers)
        provider_errors = sum(bool(row.get("error")) for row in providers)
        lines += [
            "", "## Provider-call record", "",
            f"- Gemma calls: {len(gemma_calls)}/32; Qwen calls: {len(qwen_calls)}/5; errors: {provider_errors}.",
            f"- Measured usage: {prompt_tokens:,} input tokens and {completion_tokens:,} output tokens.",
            f"- Calculated total cost: ${total_cost:.8f}; provider-confirmed billed cost: unavailable.",
            "- All successful responses contained a valid label, completion value, and non-empty reason.",
        ]
    atomic_write(REPORT_MD, "\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--local", action="store_true")
    mode.add_argument("--remote", action="store_true")
    parser.add_argument("--approved-paid-calls", action="store_true")
    parser.add_argument("--gemma-cost-per-call", type=float, default=0.0)
    parser.add_argument("--qwen-cost-per-call", type=float, default=0.0)
    args = parser.parse_args()
    if args.local:
        run_local()
        return
    if not args.approved_paid_calls:
        raise SystemExit("Remote evaluation requires explicit approval and --approved-paid-calls")
    if args.gemma_cost_per_call < 0 or args.qwen_cost_per_call < 0:
        raise SystemExit("Cost estimates cannot be negative")
    run_remote(args.gemma_cost_per_call, args.qwen_cost_per_call)


if __name__ == "__main__":
    main()
