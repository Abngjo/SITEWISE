---
license: apache-2.0
base_model: google/siglip2-base-patch16-224
datasets:
  - mfjbrr/team-QH045-sitewise-photos
tags:
  - qai-hf-hackathon-2026
  - image-classification
  - construction
  - qatar
pipeline_tag: image-classification
---

# SITEWISE construction evidence classifier (team-QH045)

Fine-tuned SigLIP2 that labels construction photos as `door`, `wall`, `ceiling` or `other`.
It is the cheap first stage of SITEWISE, an AI auditor for construction payment claims in Qatar: confident predictions stay on CPU, uncertain ones escalate to Qwen2.5-VL via Inference Providers, and every result goes to a human engineer.

**This model produces observations, not certification.** It cannot measure installed quantity or quality.

## Usage
```python
from transformers import pipeline

classifier = pipeline("image-classification", model="mfjbrr/team-QH045-sitewise")
classifier("site_photo.jpg")
```

## Data
- Dataset: [`mfjbrr/team-QH045-sitewise-photos`](https://huggingface.co/datasets/mfjbrr/team-QH045-sitewise-photos)
- 112 train and 32 test images: 28 train and 8 test per class.
- All images are from Wikimedia Commons, picked by hand from search and category results. Licences are mixed (CC0, public domain, CC BY, CC BY-SA), and `sources.csv` in the dataset gives the author, URL and licence of each image.
- The split is by photographer, so no photographer appears in both train and test.

## Training
| Setting | Value |
|---|---|
| Base model | `google/siglip2-base-patch16-224` |
| Epochs | 5 |
| Learning rate | 5e-5 |
| Batch size | 16 |
| Best epoch chosen by | Accuracy on the test split |
| Script | `finetune/train_siglip2.py` |

**Training cost on HF Jobs:** about $0.05 in total on `a10g-small` ($1.00/hour): an 80-second smoke test and a 106-second full run, 3.1 minutes together. This is calculated from runtime at list price.

## Results

**Pending: independent eval.** The comparison below will be filled in from the team's evaluation.

| Model | Accuracy | Macro F1 | Cost / photo | Avg latency |
|---|---|---|---|---|
| SigLIP2 zero-shot | pending | pending | pending | pending |
| **This model** | pending | pending | pending | pending |
| Qwen2.5-VL-7B (always) | pending | pending | pending | pending |
| SITEWISE cascade (this model + escalation) | pending | pending | pending | pending |

### Training-run check
The final model labelled all 32 images in the dataset's test split correctly (accuracy 1.00, macro F1 1.00), with a lowest top-label confidence of 0.53.

**This is not an estimate of real-world accuracy.** The same split was used to choose the best epoch, it holds only 32 hand-picked images, and it comes from the same kind of source as the training data.

## Limitations
- The dataset is small, with limited site and lighting diversity, and labels were assigned by one person from thumbnails.
- Most photos are not from Qatar or the Gulf, and many show finished work rather than work in progress. The classes are also broader than the sample project's BOQ items: `wall` includes some brick and masonry, and `ceiling` includes tiled and decorative ceilings.
- The model has not been validated on real Qatar projects.
- It labels a photo's main subject only. It cannot tell whether a door set is complete, for example whether a frame has its leaf.
- Do not use it for payment decisions without engineer review.
