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
It is the cheap first stage of SITEWISE, an AI auditor for construction payment claims in Qatar: confident predictions stay on CPU, while low-confidence photos, label mismatches and elements claimed as complete escalate to Gemma (`google/gemma-4-31B-it`, with `Qwen/Qwen2.5-VL-72B-Instruct` as fallback) via Inference Providers. Every result goes to a human engineer.

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

Evaluation on the dataset's fixed `test` split (n=32, 8 photos per class). The split was not used to tune prompts or thresholds, and it did not train the weights, but **it was used to choose this model's best epoch**, so this model's score is not fully independent. See `data/a7_evaluation/REPORT.md` for the method and `data/a7_evaluation/summary.json` for raw numbers.

| Setup | Accuracy | Macro F1 | Avg latency | Est. cost / photo | Escalation |
|---|---|---|---|---|---|
| SigLIP2 zero-shot | 96.88% | 0.969 | 0.024 s | $0.000000 | 0% |
| **This model (fine-tuned SigLIP2)** | 100.00% | 1.000 | 0.014 s | $0.000000 | 0% |
| Gemma on every photo | 100.00% | 1.000 | 3.277 s | $0.000084 | 100% |
| Cascade as tested (**zero-shot** stage 1 + Gemma) | 100.00% | 1.000 | 0.418 s | $0.000013 | 15.6% |

**What the cascade row does and doesn't measure:**
- Its first stage was zero-shot SigLIP2, not this fine-tuned model. A cascade using this model has not been measured.
- It had no completion claims. In the app, every photo of an element claimed in the current certificate goes to Gemma for a completion check, so real escalation on those photos is 100%, not 15.6%.
- For routine classification only, it was about 6.5× cheaper and 7.8× faster per photo than Gemma on every photo. Don't read that as the saving for a full payment audit.

Costs are calculated from measured token counts at published rates, not provider-confirmed billing. Local latencies come from the evaluator's machine, which may have used a GPU, so they may not match CPU hardware.

This table used an earlier Gemma prompt. The app now also asks Gemma about authenticity and stage of work, so a Gemma call costs an estimated $0.00015 to $0.00017 and took about 1 second longer in a side-by-side test. See `data/d_photo_checks/REPORT.md`.

On the team's separate 37-photo development set, this model scored 97.30% (macro F1 0.973) against 91.89% (0.921) for zero-shot. See `ai/finetuned_compatibility.md`.

**These are not real-world accuracy figures.** n=32 is small, every image was hand-picked by one person for clarity, and most are not Qatar or Gulf site photos. Zero-shot also scored 96.88%, so these test photos are easy to tell apart. Expect lower accuracy on messy, low-light or partial site photos.

## Limitations
- The dataset is small (144 images total), with limited site and lighting diversity, and labels were assigned by one person from thumbnails.
- Most photos are not from Qatar or the Gulf, and many show finished work rather than work in progress. The classes are also broader than the sample project's BOQ items: `wall` includes some brick and masonry, and `ceiling` includes tiled and decorative ceilings.
- The model has not been validated on real Qatar projects or real-site lighting and angles.
- It labels a photo's main subject only. It cannot tell whether a door set is complete, for example whether a frame has its leaf — completion is judged by the VLM stage and the human reviewer, not this classifier.
- Do not use it for payment decisions without engineer review.
