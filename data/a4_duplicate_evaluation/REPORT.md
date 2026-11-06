# A4 duplicate detection evaluation

Ten genuinely different door photos from `data/uploads/` were used as originals. Each transform was tested in both upload orders against its source and all nine similar-door negatives.

| Variant | TP | FN | FP | TN | Triggered methods |
|---|---:|---:|---:|---:|---|
| exact | 20 | 0 | 0 | 180 | sha256: 20 |
| resized | 20 | 0 | 0 | 180 | whole_phash: 20 |
| brightness | 20 | 0 | 0 | 180 | whole_phash: 20 |
| crop_center_20pct | 20 | 0 | 0 | 180 | crop_phash_dhash: 20 |
| crop_offset_20pct | 20 | 0 | 0 | 180 | crop_phash_dhash: 20 |

Precision: **100.000%**; recall: **100.000%**; false-positive rate: **0.000%**.

Total: 1000 comparisons (100 positive and 900 similar-door negative pairs). Runtime: 66.368s.

`response_kind` remains contract-compatible; `trigger_method` in `results.csv` identifies the internal detector.
