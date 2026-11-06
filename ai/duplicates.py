"""Evidence reuse detection (owner: Dev A).

Three layers, cheapest first:
  1. SHA-256 of file bytes      -> exact duplicate
  2. Perceptual hash (pHash)    -> resized / recompressed / lightly edited copies
  3. Image embeddings (SigLIP2) -> harder near-duplicates (crops); optional, plug in via `embed_fn`

Reuse is flagged for review, never called fraud: an old photo can legitimately
document cumulative progress.
"""
from __future__ import annotations

import hashlib
import io

import imagehash
from PIL import Image

PHASH_MAX_DISTANCE = 10   # tune on your test set (exact/resized/cropped copies)
EMBED_MIN_COSINE = 0.95   # tune; only used if embeddings are available


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
    """new/index items: {evidence_id, sha256, phash, embedding?, certificate_no}."""
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
    return sorted(matches, key=lambda m: -m["score"])
