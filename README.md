---
title: SITEWISE
emoji: 🏗️
colorFrom: blue
colorTo: red
sdk: docker
app_port: 7860
tags:
  - qai-hf-hackathon-2026
pinned: false
---

# SITEWISE: construction payment-claim auditor for Qatar projects

Checks a contractor's progress claim against photo evidence, the BIM model, BOQ rates and the schedule
**before** money is paid. AI observes, evidence supports, the engineer certifies.

> All project data in this Space is **fictional sample data** (Al Wakra Community Clinic, Package B).

## Quick start (local)
```bash
pip install -r requirements.txt -r requirements-dev.txt
pip install torch --index-url https://download.pytorch.org/whl/cpu
cp .env.example .env                      # add your HF_TOKEN
SITEWISE_DISABLE_MODELS=1 uvicorn backend.main:app --reload --port 7860   # stub AI, instant start
# open http://localhost:7860/docs  and  http://localhost:7860/m (mobile upload)
SITEWISE_DISABLE_MODELS=1 python -m pytest -q tests                      # 9 acceptance tests
```
Regenerate the sample building: `python scripts/make_ifc.py && python scripts/ifc_to_glb.py`

## Who owns what
| Dev | Folder | First deliverable |
|---|---|---|
| A - AI | `ai/` | Real SigLIP2 + Qwen2.5-VL calls working on 10 photos (`inference.py`), thresholds tuned, embeddings added to `duplicates.py` |
| B - Frontend | `frontend/` | Vite React app against `contracts/api.md`; 3D viewer loads `/model.glb`, recolors from `/api/model/status` |
| C - Backend (captain) | `backend/`, `Dockerfile` | Space deployed with this skeleton by 5 PM; SQLite swap optional |
| D - Data & pitch | `data/`, `scripts/`, `finetune/` | Photos on the Hub dataset repo, prior-certificate photos in `data/sample_project/photos/IPC-03/`, fine-tune job, model card, video |

## Rules
- `contracts/` is frozen after the 3 PM sync. Change it only with the whole team.
- Money, dates and critical path are computed by code. LLMs never produce figures.
- No photos or weights in git: photos go to the Hub dataset repo, weights go to the Hub model repo.
- Branch per person; C merges to `main` at 18:00, 22:00, 02:00. Deploy: `git push space main`.
- `POST /api/admin/reset` before every rehearsal and the live demo.

## Demo script (3 min)
1. Problem: on Qatar projects, contractors are paid on their own progress claims.
2. Open IPC-04: claimed QAR 123,300 vs supported QAR 24,780.
3. Judge scans the QR code → `/m` → uploads a door photo → real HF inference.
4. Reused photo from IPC-03 flagged side by side.
5. Engineer approves D-103 → 3D door turns green, supported value +QAR 6,500, report updates.
6. Schedule what-if + summer-calendar note; Arabic report; AI cost vs always-VLM.

## Hugging Face usage
SigLIP2 (transformers, in-Space CPU) → fine-tuned on HF Jobs → Hub model + dataset with cards →
Qwen2.5-VL via Inference Providers for uncertain photos only → Docker Space.

- Model: [mfjbrr/team-QH045-sitewise](https://huggingface.co/mfjbrr/team-QH045-sitewise)
- Dataset: [mfjbrr/team-QH045-sitewise-photos](https://huggingface.co/datasets/mfjbrr/team-QH045-sitewise-photos)
