# SITEWISE A6/A7 held-out evaluation

Dataset: `mfjbrr/team-QH045-sitewise-photos`, fixed `test` split, n=32 (8 images per class). The test split was not used to tune prompts, thresholds, or model weights.

| Setup | Accuracy | Macro F1 | Avg latency | Est. cost/photo | Escalation | Evaluated |
|---|---:|---:|---:|---:|---:|---:|
| siglip2_zero_shot | 96.88% | 0.969 | 0.024 s | $0.00000000 | 0.00% | 32/32 |
| siglip2_finetuned | 100.00% | 1.000 | 0.014 s | $0.00000000 | 0.00% | 32/32 |
| gemma_every_photo | 100.00% | 1.000 | 3.277 s | $0.00008407 | 100.00% | 32/32 |
| sitewise_cascade | 100.00% | 1.000 | 0.418 s | $0.00001292 | 15.62% | 32/32 |

Local model construction/download time is excluded; per-image preprocessing and inference are included. Provider latency and token counts come from real calls. The provider did not return billed amounts, so costs are calculated estimates from measured tokens and published rates. Provider calls are checkpointed and never retried automatically.

## Provider-call record

- Gemma calls: 32/32; Qwen calls: 0/5; errors: 0.
- Measured usage: 6,718 input tokens and 1,153 output tokens.
- Calculated total cost: $0.00269014; provider-confirmed billed cost: unavailable.
- All successful responses contained a valid label, completion value, and non-empty reason.
