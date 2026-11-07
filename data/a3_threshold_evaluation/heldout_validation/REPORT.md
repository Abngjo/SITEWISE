# Frozen 0.60 threshold held-out validation

This is the single validation of the preselected 0.60 candidate on Person D's untouched 32-image A7 test split. No threshold was retuned and no model or provider call was made.

| Threshold | Routed accuracy | Macro F1 | Escalated | Avg routed latency | Est. cost/photo |
|---:|---:|---:|---:|---:|---:|
| 0.60 | 100.00% | 1.000 | 3/32 (9.38%) | 0.300s | $0.00000785 |
| 0.80 | 100.00% | 1.000 | 5/32 (15.62%) | 0.418s | $0.00001292 |

## Routing details

### 0.60

- Low confidence only: test/wall/wall_004.jpg, test/wall/wall_005.jpg
- Declared-category mismatch only: test/ceiling/ceiling_004.jpg
- Both reasons: none
- Incorrect predictions not escalated: none
- Measured tokens routed: 632 input, 106 output.

### 0.80

- Low confidence only: test/ceiling/ceiling_006.jpg, test/ceiling/ceiling_007.jpg, test/wall/wall_004.jpg, test/wall/wall_005.jpg
- Declared-category mismatch only: none
- Both reasons: test/ceiling/ceiling_004.jpg
- Incorrect predictions not escalated: none
- Measured tokens routed: 1042 input, 174 output.

## Zero-shot error

`test/ceiling/ceiling_004.jpg` was predicted `other` instead of `ceiling` at normalized score 0.776226. It escalated at 0.60 because of `declared_category_mismatch`. Gemma predicted `ceiling`, so the error was fixed.

Accuracy, F1, routing, latency, and token counts above are reconstructed from measured saved responses. Costs are token-based estimates; provider-confirmed billing unavailable.

## Recommendation

At 0.60 the routed result remains 100% accurate while using 3 rather than 5 Gemma calls. However, the sole SigLIP error scores 0.776226 and is caught only by category mismatch at 0.60. Because the current upload API permits `element_id=None`, 0.60 is safe only for workflows that guarantee a valid declared category. Do not adopt it globally for optional-category uploads without an additional guard or validation set covering missing and incorrect declarations.
