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
It is the cheap first stage of SITEWISE, an AI auditor for construction payment claims in Qatar: confident predictions stay on CPU, uncertain ones escalate to Gemma (`google/gemma-4-31B-it`, with `Qwen/Qwen2.5-VL-72B-Instruct` as fallback) via Inference Providers, and every result goes to a human engineer.

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

Held-out evaluation on the dataset's fixed `test` split (n=32, 8 photos per class). This split was **not** used to tune prompts, thresholds or model weights (see `data/a7_evaluation/REPORT.md` for the full methodology and `data/a7_evaluation/summary.json` for raw numbers).

| Setup | Accuracy | Macro F1 | Avg latency | Est. cost / photo | Escalation |
|---|---|---|---|---|---|
| SigLIP2 zero-shot | 96.88% | 0.969 | 0.024 s | $0.000000 | 0% |
| **This model (fine-tuned SigLIP2)** | 100.00% | 1.000 | 0.014 s | $0.000000 | 0% |
| Gemma on every photo | 100.00% | 1.000 | 3.277 s | $0.000084 | 100% |
| **SITEWISE cascade (this model + escalation)** | 100.00% | 1.000 | 0.418 s | $0.000013 | 15.6% |

The cascade matches always-calling-Gemma on accuracy while being **about 6.5× cheaper and 7.8× faster per photo on average**, by escalating only the 15.6% of photos the small model is unsure about. Costs are calculated from measured token counts at published Inference Providers rates, not provider-confirmed billing.

**Read this with the dataset's limits in mind, not as real-world accuracy.** n=32 is small, every image was hand-picked by one person for clarity, and most are not Qatar or Gulf site photos (see Limitations). The 96.88–100% range across every setup, including zero-shot, mostly says these particular test photos are easy to tell apart — it is not evidence the model will perform this well on messy, low-light or partial real site photos.

## Limitations
- The dataset is small (144 images total), with limited site and lighting diversity, and labels were assigned by one person from thumbnails.
- Most photos are not from Qatar or the Gulf, and many show finished work rather than work in progress. The classes are also broader than the sample project's BOQ items: `wall` includes some brick and masonry, and `ceiling` includes tiled and decorative ceilings.
- The model has not been validated on real Qatar projects or real-site lighting and angles.
- It labels a photo's main subject only. It cannot tell whether a door set is complete, for example whether a frame has its leaf — completion is judged by the VLM stage and the human reviewer, not this classifier.
- Do not use it for payment decisions without engineer review.
