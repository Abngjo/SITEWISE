---
license: apache-2.0
base_model: google/siglip2-base-patch16-224
tags:
  - qai-hf-hackathon-2026
  - image-classification
  - construction
  - qatar
pipeline_tag: image-classification
---

# SITEWISE construction evidence classifier (team-NN)

Fine-tuned SigLIP2 that labels construction progress photos as `door`, `wall` (blockwork), `ceiling` (suspended) or `other`.
It is the cheap first stage of SITEWISE: confident predictions stay on CPU; uncertain ones escalate to Qwen2.5-VL via Inference Providers; every result goes to a human engineer.

**This model produces observations, not certification.** It cannot measure installed quantity or quality.

## Data
- Dataset: `CAPTAIN/team-NN-sitewise-photos` (N train / M test images, licensed/public or self-taken; sources listed in the dataset card)
- Train/test split by source where possible.

## Results (held-out test set) - FILL IN FROM THE JOB OUTPUT
| Model | Accuracy | Macro F1 | Cost / photo | Avg latency |
|---|---|---|---|---|
| SigLIP2 zero-shot | | | | |
| **This model** | | | | |
| Qwen2.5-VL-7B (always) | | | | |
| SITEWISE cascade (this model + escalation) | | | | |

Training cost on HF Jobs: $X (flavor, minutes).

## Limitations
Small dataset, limited site/lighting diversity, not validated on real Qatar projects. Do not use for payment decisions without engineer review.
