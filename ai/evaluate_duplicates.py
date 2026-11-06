"""Evaluate duplicate transforms and similar-door negatives without model calls."""
from __future__ import annotations

import csv
import json
import shutil
import tempfile
import time
from collections import Counter
from pathlib import Path

import imagehash
from PIL import Image, ImageEnhance

from ai import duplicates

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "a4_duplicate_evaluation"


def record(path: Path, evidence_id: str) -> dict:
    data = path.read_bytes()
    return {
        "evidence_id": evidence_id,
        "path": str(path),
        "certificate_no": "A4-EVAL",
        "sha256": duplicates.sha256_bytes(data),
        "phash": duplicates.phash_bytes(data),
    }


def trigger_method(query: dict, candidate: dict, match: dict | None) -> str:
    if not match:
        return ""
    if match["kind"] == "exact":
        return "sha256"
    if match["kind"] == "near_duplicate_embedding":
        return "siglip2_embedding"
    distance = imagehash.hex_to_hash(query["phash"]) - imagehash.hex_to_hash(candidate["phash"])
    return "whole_phash" if distance <= duplicates.PHASH_MAX_DISTANCE else "crop_phash_dhash"


def save_variant(source: Path, target: Path, variant: str) -> None:
    if variant == "exact":
        shutil.copyfile(source, target)
        return
    with Image.open(source) as opened:
        image = opened.convert("RGB")
    width, height = image.size
    if variant == "resized":
        image = image.resize((max(1, width // 2), max(1, height // 2)))
    elif variant == "brightness":
        image = ImageEnhance.Brightness(image).enhance(1.35)
    elif variant == "crop_center_20pct":
        image = image.crop((round(width * .1), round(height * .1),
                            round(width * .9), round(height * .9)))
    elif variant == "crop_offset_20pct":
        image = image.crop((round(width * .2), round(height * .05),
                            width, round(height * .85)))
    else:
        raise ValueError(variant)
    image.save(target, format="JPEG", quality=85)


def main() -> None:
    sources = sorted((ROOT / "data" / "uploads").glob("door*.jpg"))
    if len(sources) != 10:
        raise SystemExit(f"Expected 10 labeled door photos in data/uploads; found {len(sources)}")
    variants = ("exact", "resized", "brightness", "crop_center_20pct", "crop_offset_20pct")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    started = time.perf_counter()

    with tempfile.TemporaryDirectory(prefix="sitewise-a4-") as temporary:
        temp = Path(temporary)
        originals = {source.stem: record(source, source.stem) for source in sources}
        transformed: dict[str, dict[str, dict]] = {variant: {} for variant in variants}
        for source in sources:
            for variant in variants:
                target = temp / f"{source.stem}_{variant}.jpg"
                save_variant(source, target, variant)
                transformed[variant][source.stem] = record(target, f"{source.stem}_{variant}")

        def compare(source_name: str, variant: str, query: dict,
                    candidates: dict[str, dict], direction: str) -> None:
            matches = {item["evidence_id"]: item
                       for item in duplicates.find_duplicates(query, list(candidates.values()))}
            for candidate_name, candidate in candidates.items():
                match = matches.get(candidate["evidence_id"])
                expected = candidate_name == source_name
                detected = match is not None
                rows.append({
                    "source": source_name,
                    "variant": variant,
                    "direction": direction,
                    "candidate": candidate_name,
                    "expected_duplicate": expected,
                    "detected": detected,
                    "outcome": ("TP" if detected else "FN") if expected else ("FP" if detected else "TN"),
                    "response_kind": match["kind"] if match else "",
                    "trigger_method": trigger_method(query, candidate, match),
                    "score": match["score"] if match else "",
                })

        for variant in variants:
            for source_name, query in transformed[variant].items():
                compare(source_name, variant, query, originals, "variant_to_original")
            for source_name, query in originals.items():
                compare(source_name, variant, query, transformed[variant], "original_to_variant")

    counts = Counter(row["outcome"] for row in rows)
    precision = counts["TP"] / (counts["TP"] + counts["FP"]) if counts["TP"] + counts["FP"] else 0
    recall = counts["TP"] / (counts["TP"] + counts["FN"]) if counts["TP"] + counts["FN"] else 0
    method_counts = Counter(row["trigger_method"] for row in rows if row["detected"])
    summary = {
        "sources": len(sources),
        "positive_pairs": counts["TP"] + counts["FN"],
        "similar_door_negative_pairs": counts["FP"] + counts["TN"],
        "TP": counts["TP"], "FN": counts["FN"], "FP": counts["FP"], "TN": counts["TN"],
        "precision": precision, "recall": recall,
        "false_positive_rate": counts["FP"] / (counts["FP"] + counts["TN"]),
        "trigger_methods": dict(method_counts),
        "runtime_s": time.perf_counter() - started,
    }
    with (OUTPUT / "results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (OUTPUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    variant_lines = []
    for variant in variants:
        group = [row for row in rows if row["variant"] == variant]
        group_counts = Counter(row["outcome"] for row in group)
        methods = Counter(row["trigger_method"] for row in group if row["detected"])
        variant_lines.append(
            f"| {variant} | {group_counts['TP']} | {group_counts['FN']} | "
            f"{group_counts['FP']} | {group_counts['TN']} | "
            f"{', '.join(f'{key}: {value}' for key, value in sorted(methods.items()))} |"
        )
    report = [
        "# A4 duplicate detection evaluation", "",
        "Ten genuinely different door photos from `data/uploads/` were used as originals. "
        "Each transform was tested in both upload orders against its source and all nine similar-door negatives.", "",
        "| Variant | TP | FN | FP | TN | Triggered methods |",
        "|---|---:|---:|---:|---:|---|", *variant_lines, "",
        f"Precision: **{precision:.3%}**; recall: **{recall:.3%}**; "
        f"false-positive rate: **{summary['false_positive_rate']:.3%}**.", "",
        f"Total: {len(rows)} comparisons ({summary['positive_pairs']} positive and "
        f"{summary['similar_door_negative_pairs']} similar-door negative pairs). Runtime: {summary['runtime_s']:.3f}s.", "",
        "`response_kind` remains contract-compatible; `trigger_method` in `results.csv` identifies the internal detector.",
    ]
    (OUTPUT / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
