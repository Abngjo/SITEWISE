"""Test the extra Gemma questions on real, AI-generated and edited photos (owner: Dev D).

Calls the same stage2_vlm() the app uses, once per image. Provider calls are billed and never
retried by this script. Writes results.csv and summary.json to data/d_photo_checks.
Images stay outside git. Run with HF_TOKEN set:
  python scripts/evaluate_photo_checks.py --real data/d1_photos/test --ai DIR --edited DIR --frames DIR
"""
import argparse, csv, json, random, sys, time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ai import inference  # noqa: E402

RATES = {"input": 0.27, "output": 0.76}  # USD per million Gemma tokens, as used in data/a7_evaluation
A7 = {"accuracy": 1.0, "avg_latency_s": 3.277, "cost_per_call_usd": 0.000084}  # same split, old prompt
OUT = ROOT / "data" / "d_photo_checks"


def make_edited(real: Path, out: Path, count: int = 6) -> None:
    """Crude cut-and-paste fakes: a door photo pasted onto a wall photo with hard edges."""
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(7)
    walls, doors = sorted((real / "wall").glob("*.jpg")), sorted((real / "door").glob("*.jpg"))
    for i in range(count):
        base = Image.open(walls[i % len(walls)]).convert("RGB")
        patch = Image.open(doors[i % len(doors)]).convert("RGB")
        patch.thumbnail((base.width // 2, int(base.height * 0.75)))
        base.paste(patch, (rng.randint(0, base.width - patch.width), base.height - patch.height))
        base.save(out / f"door_edit_{i}.jpg", quality=90)


def jobs(args) -> list[dict]:
    rows = []
    for folder in sorted(p for p in Path(args.real).iterdir() if p.is_dir()):
        for path in sorted(folder.glob("*.jpg")):
            rows.append(dict(group="real_unclaimed", path=path, truth=folder.name, claimed=False))
            if folder.name != "other":
                rows.append(dict(group="real_claimed", path=path, truth=folder.name, claimed=True))
    for group, folder in (("ai_generated", args.ai), ("edited", args.edited), ("door_frame_no_leaf", args.frames)):
        for path in sorted(Path(folder).iterdir()):
            if path.suffix.lower() in (".jpg", ".webp"):
                rows.append(dict(group=group, path=path, truth=path.stem.split("_")[0], claimed=True))
    return rows


def run(job: dict) -> dict:
    img = Image.open(job["path"]).convert("RGB")
    img.thumbnail((768, 768))  # same as the app
    started = time.perf_counter()
    row = {"group": job["group"], "image": job["path"].name, "truth": job["truth"], "claimed": job["claimed"]}
    try:
        vlm = inference.stage2_vlm(img, job["truth"], job["claimed"])
        calls = vlm.pop("_metering")["calls"]
        row.update({k: vlm.get(k) for k in ("label", "completion", "phase", "authenticity", "authenticity_reason", "reason", "model")})
        row.update(input_tokens=sum(c["input_tokens"] or 0 for c in calls), output_tokens=sum(c["output_tokens"] or 0 for c in calls),
                   calls=len(calls), error="")
    except Exception as e:
        row.update(error=f"{type(e).__name__}: {e}"[:200], calls=len(getattr(e, "calls", [])), input_tokens=0, output_tokens=0)
    row["latency_s"] = round(time.perf_counter() - started, 3)
    return row


def main():
    ap = argparse.ArgumentParser()
    for name in ("real", "ai", "edited", "frames"):
        ap.add_argument(f"--{name}", required=True)
    args = ap.parse_args()
    make_edited(Path(args.real), Path(args.edited))
    with ThreadPoolExecutor(4) as ex:
        rows = list(ex.map(run, jobs(args)))
    OUT.mkdir(parents=True, exist_ok=True)
    fields = ["group", "image", "truth", "claimed", "label", "completion", "phase", "authenticity", "authenticity_reason",
              "reason", "model", "input_tokens", "output_tokens", "calls", "latency_s", "error"]
    with open(OUT / "results.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fields, extrasaction="ignore"); w.writeheader(); w.writerows(rows)
    groups = {}
    for name in dict.fromkeys(r["group"] for r in rows):
        rs = [r for r in rows if r["group"] == name]; ok = [r for r in rs if not r["error"]]
        groups[name] = {
            "n": len(rs), "errors": len(rs) - len(ok),
            "authenticity": dict(Counter(r["authenticity"] for r in ok)),
            "flagged": sum(r["authenticity"] in ("possibly_ai_generated", "possibly_edited") for r in ok),
            "label_accuracy": round(sum(r["label"] == r["truth"] for r in ok) / len(rs), 4) if rs else None,
            "completion": dict(Counter(r["completion"] for r in ok)), "phase": dict(Counter(str(r["phase"]) for r in ok)),
            "avg_latency_s": round(sum(r["latency_s"] for r in ok) / max(1, len(ok)), 3),
            "avg_input_tokens": round(sum(r["input_tokens"] for r in ok) / max(1, len(ok)), 1),
            "avg_output_tokens": round(sum(r["output_tokens"] for r in ok) / max(1, len(ok)), 1),
        }
        g = groups[name]; g["est_cost_per_call_usd"] = round((g["avg_input_tokens"] * RATES["input"] + g["avg_output_tokens"] * RATES["output"]) / 1e6, 7)
    total = sum((r["input_tokens"] * RATES["input"] + r["output_tokens"] * RATES["output"]) / 1e6 for r in rows)
    summary = {"model": inference.VLM_MODEL, "calls": len(rows), "models_used": dict(Counter(str(r.get("model")) for r in rows)),
               "est_total_cost_usd": round(total, 5), "a7_old_prompt": A7, "groups": groups}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
