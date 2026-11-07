"""Evidence reuse detection (owner: Dev A).

Three layers, cheapest first:
  1. SHA-256 of file bytes      -> exact duplicate
  2. Perceptual hash (pHash)    -> resized / recompressed / lightly edited copies
  3. Image embeddings (SigLIP2) -> harder near-duplicates (crops); optional, plug in via `embed_fn`

When evidence records have readable local paths, a cached multi-scale pHash +
dHash fallback checks moderate crops without replacing the existing methods.

Reuse is flagged for review, never called fraud: an old photo can legitimately
document cumulative progress.
"""
from __future__ import annotations

import hashlib
import io
from functools import lru_cache
from pathlib import Path

import imagehash
from PIL import Image

PHASH_MAX_DISTANCE = 10   # tune on your test set (exact/resized/cropped copies)
EMBED_MIN_COSINE = 0.95   # tune; only used if embeddings are available
CROP_PHASH_MAX_DISTANCE = 6
CROP_DHASH_MAX_DISTANCE = 8


@lru_cache(maxsize=128)
def _crop_signatures(path: str, mtime_ns: int, size: int):
    """Return whole-image and multi-scale window hashes for a local image.

    The cache key includes file metadata so replaced uploads are re-read. The
    bounded cache avoids retaining signatures for an unbounded upload history.
    """
    with Image.open(path) as source:
        image = source.convert("RGB")
    image.thumbnail((512, 512))

    def signature(candidate):
        return imagehash.phash(candidate), imagehash.dhash(candidate)

    whole = signature(image)
    windows = []
    width, height = image.size
    for scale in (0.6, 0.7, 0.8, 0.9):
        for x_position in (0, 0.25, 0.5, 0.75, 1):
            for y_position in (0, 0.25, 0.5, 0.75, 1):
                left = round(width * (1 - scale) * x_position)
                top = round(height * (1 - scale) * y_position)
                right = left + round(width * scale)
                bottom = top + round(height * scale)
                windows.append(signature(image.crop((left, top, right, bottom))))
    return whole, windows


def _local_signatures(item):
    if not item.get("path"):
        return None
    try:
        path = Path(item["path"]).resolve()
        stat = path.stat()
        return _crop_signatures(str(path), stat.st_mtime_ns, stat.st_size)
    except (OSError, ValueError):
        return None


def _crop_match_score(first, second):
    if first is None or second is None:
        return None
    # Compare the whole image to regions of the other in both upload orders.
    best = None
    for whole, windows in ((first[0], second[1]), (second[0], first[1])):
        for phash, dhash in windows:
            phash_distance = whole[0] - phash
            dhash_distance = whole[1] - dhash
            if (phash_distance <= CROP_PHASH_MAX_DISTANCE
                    and dhash_distance <= CROP_DHASH_MAX_DISTANCE):
                score = round(1 - max(phash_distance, dhash_distance) / 64, 3)
                best = max(best or 0, score)
    return best


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def phash_bytes(b: bytes) -> str:
    return str(imagehash.phash(Image.open(io.BytesIO(b)).convert("RGB")))


def _cos(a, b) -> float:
    num = sum(x * y for x, y in zip(a, b))
    da = sum(x * x for x in a) ** 0.5
    db = sum(y * y for y in b) ** 0.5
    return num / (da * db + 1e-12)


def find_duplicates(new: dict, index: list[dict]) -> list[dict]:
    """new/index items may also contain local ``path`` values for crop checks."""
    matches = []
    for old in index:
        if old["evidence_id"] == new["evidence_id"]:
            continue
        if old["sha256"] == new["sha256"]:
            matches.append({"evidence_id": old["evidence_id"], "certificate_no": old.get("certificate_no"),
                            "kind": "exact", "score": 1.0})
            continue
        dist = imagehash.hex_to_hash(old["phash"]) - imagehash.hex_to_hash(new["phash"])
        if dist <= PHASH_MAX_DISTANCE:
            matches.append({"evidence_id": old["evidence_id"], "certificate_no": old.get("certificate_no"),
                            "kind": "near_duplicate_phash", "score": round(1 - dist / 64, 3)})
            continue
        if old.get("embedding") and new.get("embedding"):
            c = _cos(old["embedding"], new["embedding"])
            if c >= EMBED_MIN_COSINE:
                matches.append({"evidence_id": old["evidence_id"], "certificate_no": old.get("certificate_no"),
                                "kind": "near_duplicate_embedding", "score": round(c, 3)})
                continue
        crop_score = _crop_match_score(_local_signatures(new), _local_signatures(old))
        if crop_score is not None:
            # Keep the captain's public response vocabulary and shape unchanged.
            matches.append({"evidence_id": old["evidence_id"], "certificate_no": old.get("certificate_no"),
                            "kind": "near_duplicate_phash", "score": crop_score})
    return sorted(matches, key=lambda m: -m["score"])
