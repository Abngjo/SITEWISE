"""Crop-hash regression tests; generated locally with no model or network."""
import random
import os
from pathlib import Path

from PIL import Image

os.environ["SITEWISE_DISABLE_MODELS"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

from ai import duplicates


def _record(tmp_path: Path, name: str, image: Image.Image) -> dict:
    path = tmp_path / f"{name}.png"
    image.save(path)
    data = path.read_bytes()
    return {
        "evidence_id": name,
        "path": str(path),
        "sha256": duplicates.sha256_bytes(data),
        "phash": duplicates.phash_bytes(data),
        "certificate_no": "TEST",
    }


def _noise(seed: int) -> Image.Image:
    return Image.frombytes("RGB", (128, 128), random.Random(seed).randbytes(128 * 128 * 3))


def test_crops_match_in_both_upload_orders_without_false_positive(tmp_path):
    original = _record(tmp_path, "original", _noise(7))
    crop = _record(tmp_path, "crop", _noise(7).crop((19, 19, 109, 109)))
    unrelated = _record(tmp_path, "unrelated", _noise(91))

    for new, old in ((crop, original), (original, crop)):
        result = duplicates.find_duplicates(new, [old, unrelated])
        assert len(result) == 1
        assert result[0]["evidence_id"] == old["evidence_id"]
        assert result[0]["kind"] == "near_duplicate_phash"
        assert set(result[0]) == {"evidence_id", "certificate_no", "kind", "score"}


def test_exact_priority_self_exclusion_and_embedding_priority(tmp_path):
    original = _record(tmp_path, "original", _noise(7))
    assert duplicates.find_duplicates(original, [original]) == []
    clone = dict(original, evidence_id="clone")
    assert duplicates.find_duplicates(clone, [original])[0]["kind"] == "exact"

    crop = _record(tmp_path, "crop", _noise(7).crop((19, 19, 109, 109)))
    original["embedding"] = [1.0, 0.0]
    crop["embedding"] = [0.96, 0.28]
    assert duplicates.find_duplicates(crop, [original])[0]["kind"] == "near_duplicate_embedding"


def test_missing_paths_preserve_existing_hash_behavior(tmp_path):
    original = _record(tmp_path, "original", _noise(7))
    clone = dict(original, evidence_id="clone", sha256="different", path=None)
    assert duplicates.find_duplicates(clone, [original])[0]["kind"] == "near_duplicate_phash"

    crop = _record(tmp_path, "crop", _noise(7).crop((19, 19, 109, 109)))
    crop["path"] = str(tmp_path / "missing.png")
    assert duplicates.find_duplicates(crop, [original]) == []


def test_crop_signature_cache_invalidates_on_file_change(tmp_path):
    original = _record(tmp_path, "original", _noise(7))
    first = duplicates._local_signatures(original)
    Image.new("RGB", (80, 80), "red").save(original["path"])
    second = duplicates._local_signatures(original)
    assert str(first[0][0]) != str(second[0][0])
