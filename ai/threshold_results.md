# A3: normalized SigLIP2 escalation threshold evaluation

## Method

Thresholds were selected on the 37 existing filename-labeled development photos in `data/uploads/`. Person D's 32-image held-out test split was not read or used. Predictions are real outputs from the captain's current `inference.stage1`; `score` is the normalized four-class share and `raw_score` is not used.

Provider cost uses **$0.00008407 per escalation** (A7 mean from measured tokens; calculated_from_provider_tokens). There are no saved current-Gemma responses for these 37 photos, so post-escalation cascade accuracy is **not measured**. No fallback labels are mocked or inferred.

| Threshold | SigLIP accuracy | Macro F1 | Escalated | Est. cost/photo | Low only | Mismatch only | Both | Incorrect not escalated |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.50 | 91.89% | 0.921 | 3/37 (8.11%) | $0.00000682 | 0 | 3 | 0 | 0 |
| 0.55 | 91.89% | 0.921 | 3/37 (8.11%) | $0.00000682 | 0 | 2 | 1 | 0 |
| 0.60 | 91.89% | 0.921 | 3/37 (8.11%) | $0.00000682 | 0 | 2 | 1 | 0 |
| 0.65 | 91.89% | 0.921 | 6/37 (16.22%) | $0.00001363 | 3 | 2 | 1 | 0 |
| 0.70 | 91.89% | 0.921 | 6/37 (16.22%) | $0.00001363 | 3 | 2 | 1 | 0 |
| 0.75 | 91.89% | 0.921 | 7/37 (18.92%) | $0.00001590 | 4 | 1 | 2 | 0 |
| 0.80 | 91.89% | 0.921 | 10/37 (27.03%) | $0.00002272 | 7 | 0 | 3 | 0 |
| 0.85 | 91.89% | 0.921 | 11/37 (29.73%) | $0.00002499 | 8 | 0 | 3 | 0 |
| 0.90 | 91.89% | 0.921 | 14/37 (37.84%) | $0.00003181 | 11 | 0 | 3 | 0 |
| 0.95 | 91.89% | 0.921 | 19/37 (51.35%) | $0.00004317 | 16 | 0 | 3 | 0 |

## Escalated photos by threshold

### 0.50

- Low confidence only: none
- Declared-category mismatch only: `other (9).jpg`, `wall (2).jpg`, `wall.jpg`
- Both reasons: none
- Incorrect predictions avoiding escalation: none

### 0.55

- Low confidence only: none
- Declared-category mismatch only: `other (9).jpg`, `wall.jpg`
- Both reasons: `wall (2).jpg`
- Incorrect predictions avoiding escalation: none

### 0.60

- Low confidence only: none
- Declared-category mismatch only: `other (9).jpg`, `wall.jpg`
- Both reasons: `wall (2).jpg`
- Incorrect predictions avoiding escalation: none

### 0.65

- Low confidence only: `ceiling.jpg`, `wall (8).jpg`, `wall (9).jpg`
- Declared-category mismatch only: `other (9).jpg`, `wall.jpg`
- Both reasons: `wall (2).jpg`
- Incorrect predictions avoiding escalation: none

### 0.70

- Low confidence only: `ceiling.jpg`, `wall (8).jpg`, `wall (9).jpg`
- Declared-category mismatch only: `other (9).jpg`, `wall.jpg`
- Both reasons: `wall (2).jpg`
- Incorrect predictions avoiding escalation: none

### 0.75

- Low confidence only: `ceiling.jpg`, `wall (5).jpg`, `wall (8).jpg`, `wall (9).jpg`
- Declared-category mismatch only: `wall.jpg`
- Both reasons: `other (9).jpg`, `wall (2).jpg`
- Incorrect predictions avoiding escalation: none

### 0.80

- Low confidence only: `ceiling.jpg`, `wall (3).jpg`, `wall (5).jpg`, `wall (6).jpg`, `wall (7).jpg`, `wall (8).jpg`, `wall (9).jpg`
- Declared-category mismatch only: none
- Both reasons: `other (9).jpg`, `wall (2).jpg`, `wall.jpg`
- Incorrect predictions avoiding escalation: none

### 0.85

- Low confidence only: `ceiling.jpg`, `wall (3).jpg`, `wall (4).jpg`, `wall (5).jpg`, `wall (6).jpg`, `wall (7).jpg`, `wall (8).jpg`, `wall (9).jpg`
- Declared-category mismatch only: none
- Both reasons: `other (9).jpg`, `wall (2).jpg`, `wall.jpg`
- Incorrect predictions avoiding escalation: none

### 0.90

- Low confidence only: `ceiling (1).jpg`, `ceiling.jpg`, `door (6).jpg`, `wall (1).jpg`, `wall (3).jpg`, `wall (4).jpg`, `wall (5).jpg`, `wall (6).jpg`, `wall (7).jpg`, `wall (8).jpg`, `wall (9).jpg`
- Declared-category mismatch only: none
- Both reasons: `other (9).jpg`, `wall (2).jpg`, `wall.jpg`
- Incorrect predictions avoiding escalation: none

### 0.95

- Low confidence only: `ceiling (1).jpg`, `ceiling (3).jpg`, `ceiling (4).jpg`, `ceiling (5).jpg`, `ceiling (7).jpg`, `ceiling.jpg`, `door (6).jpg`, `other (6).jpg`, `wall (1).jpg`, `wall (3).jpg`, `wall (4).jpg`, `wall (5).jpg`, `wall (6).jpg`, `wall (7).jpg`, `wall (8).jpg`, `wall (9).jpg`
- Declared-category mismatch only: none
- Both reasons: `other (9).jpg`, `wall (2).jpg`, `wall.jpg`
- Incorrect predictions avoiding escalation: none

## Recommendation

Thresholds 0.50–0.60 tie for the lowest escalation rate and cost. **0.60** is the efficient provisional choice at the top of that plateau: 8.11% escalation and $0.00000682/photo, with no additional calls versus 0.50. The declared-category mismatch rule still routes every observed SigLIP error, so no incorrect development prediction avoids escalation.

It is **not yet safe to adopt as a production default**. The development set is small, the declared label makes mismatch routing unusually informative, and current-Gemma post-escalation accuracy is unavailable for these photos. Validate the frozen candidate once on Person D's untouched held-out split and retain human review before changing the live threshold.

## Reproduce

```powershell
.\.venv\Scripts\python.exe -m ai.evaluate_thresholds --refresh
```

`development_predictions.csv` caches image SHA-256 values and normalized model outputs; `threshold_details.csv` records the routing reason for every photo and threshold.
