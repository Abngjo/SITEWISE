"""Two-stage image analysis router (owner: Dev A).

Stage 1: small model inside the Space (SigLIP2 zero-shot, or your fine-tuned checkpoint).
Stage 2: only if stage 1 is uncertain or disagrees with the declared element ->
         Qwen2.5-VL via Hugging Face Inference Providers.
Output is an OBSERVATION. `completion_certified` is always False.

Env vars:
  HF_TOKEN                   token (Space secret / local .env)
  SITEWISE_STAGE1_MODEL      default google/siglip2-base-patch16-224 (zero-shot)
  SITEWISE_FINETUNED_MODEL   e.g. CAPTAIN/team-NN-sitewise (image-classification head); overrides zero-shot
  SITEWISE_VLM_MODEL         default Qwen/Qwen2.5-VL-7B-Instruct
  SITEWISE_ESCALATION_THRESHOLD  default 0.80 (calibrate on your eval set!)
  SITEWISE_VLM_COST_USD      estimated cost per escalated call, for the cost log (replace with real numbers)
  SITEWISE_DISABLE_MODELS=1  return stub predictions (for frontend/backend dev without models)
"""
from __future__ import annotations

import base64
import io
import json
import os
import time

from PIL import Image

# Visual classes <-> BIM element types. Keep in sync with contracts/schemas.json.
LABELS = {
    "door": "a photo of an installed interior door in a building under construction",
    "wall": "a photo of a concrete blockwork wall under construction",
    "ceiling": "a photo of a suspended ceiling being installed",
    "other": "a photo of a construction site with no door, wall or ceiling work visible",
}
STAGE1_MODEL = os.getenv("SITEWISE_STAGE1_MODEL", "google/siglip2-base-patch16-224")
FINETUNED_MODEL = os.getenv("SITEWISE_FINETUNED_MODEL", "")
VLM_MODEL = os.getenv("SITEWISE_VLM_MODEL", "Qwen/Qwen2.5-VL-7B-Instruct")
THRESHOLD = float(os.getenv("SITEWISE_ESCALATION_THRESHOLD", "0.80"))
VLM_COST = float(os.getenv("SITEWISE_VLM_COST_USD", "0.002"))
DISABLED = os.getenv("SITEWISE_DISABLE_MODELS") == "1"

_pipe = None
COST_LOG: list[dict] = []


def _stage1_pipe():
    global _pipe
    if _pipe is None:
        from transformers import pipeline
        if FINETUNED_MODEL:
            _pipe = ("ft", pipeline("image-classification", model=FINETUNED_MODEL))
        else:
            _pipe = ("zs", pipeline("zero-shot-image-classification", model=STAGE1_MODEL))
    return _pipe


def stage1(img: Image.Image) -> list[dict]:
    kind, pipe = _stage1_pipe()
    if kind == "ft":
        return [{"label": r["label"], "score": float(r["score"])} for r in pipe(img, top_k=len(LABELS))]
    prompts = list(LABELS.values())
    res = pipe(img, candidate_labels=prompts)
    inv = {v: k for k, v in LABELS.items()}
    return [{"label": inv[r["label"]], "score": float(r["score"])} for r in res]


def stage2_vlm(img: Image.Image, declared_type: str | None) -> dict:
    from huggingface_hub import InferenceClient
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=85)
    url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    prompt = (
        "You are assisting a construction site engineer. Look at the photo and answer ONLY with JSON: "
        '{"label": one of ["door","wall","ceiling","other"], '
        '"completion": one of ["complete","partial","not_started","unclear"], '
        '"reason": "<one short sentence>"}. '
        f"The contractor says this photo shows a {declared_type or 'construction element'}."
    )
    client = InferenceClient(token=os.getenv("HF_TOKEN"))
    out = client.chat_completion(
        model=VLM_MODEL,
        messages=[{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": url}},
            {"type": "text", "text": prompt}]}],
        max_tokens=150,
    )
    text = out.choices[0].message.content
    try:
        return json.loads(text[text.find("{"): text.rfind("}") + 1])
    except Exception:
        return {"label": "other", "completion": "unclear", "reason": text[:200]}


_emb = None
_CACHE: dict[str, dict] = {}


def warm_up() -> dict:
    """Load models once at startup so the first demo upload isn't slow."""
    if DISABLED:
        return {"warm": False, "reason": "SITEWISE_DISABLE_MODELS=1"}
    t0 = time.time()
    try:
        _stage1_pipe()
        stage1(Image.new("RGB", (224, 224), (128, 128, 128)))
        _embedder()
        return {"warm": True, "seconds": round(time.time() - t0, 1)}
    except Exception as e:
        return {"warm": False, "error": str(e)}


def _embedder():
    global _emb
    if _emb is None:
        from transformers import AutoModel, AutoProcessor
        _emb = (AutoModel.from_pretrained(STAGE1_MODEL).eval(), AutoProcessor.from_pretrained(STAGE1_MODEL))
    return _emb


def embed(image_bytes: bytes) -> list[float] | None:
    """L2-normalised SigLIP2 image embedding for near-duplicate checks. None if unavailable."""
    if DISABLED:
        return None
    try:
        import torch
        model, proc = _embedder()
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        with torch.no_grad():
            f = model.get_image_features(**proc(images=img, return_tensors="pt"))
        f = f / f.norm(dim=-1, keepdim=True)
        return [round(float(x), 5) for x in f[0]]
    except Exception:
        return None


def analyze(image_bytes: bytes, evidence_id: str, declared_type: str | None) -> dict:
    import hashlib
    key = hashlib.sha256(image_bytes).hexdigest() + f":{declared_type}"
    if key in _CACHE:  # identical photo already analysed: reuse result, zero cost
        hit = {**_CACHE[key], "evidence_id": evidence_id, "est_cost_usd": 0.0, "cache_hit": True}
        COST_LOG.append({"evidence_id": evidence_id, "stage": "cache", "latency_s": 0.0, "est_cost_usd": 0.0})
        return hit
    res = _analyze(image_bytes, evidence_id, declared_type)
    _CACHE[key] = res
    return res


def _analyze(image_bytes: bytes, evidence_id: str, declared_type: str | None) -> dict:
    t0 = time.time()
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img.thumbnail((768, 768))  # cost/latency: no need for full resolution

    if DISABLED:
        obs = [{"label": declared_type or "other", "score": 0.5}]
        result = {"stage": "stub", "observations": obs, "escalated": False, "vlm": None}
    else:
        stage1_error = None
        try:
            obs = stage1(img)
        except Exception as e:  # model failed to load -> graceful review-needed state
            obs = [{"label": "other", "score": 0.0}]
            stage1_error = str(e)
        top = max(obs, key=lambda o: o["score"])
        mismatch = declared_type is not None and top["label"] != declared_type
        escalate = top["score"] < THRESHOLD or mismatch
        result = {"stage": "stage1", "observations": obs, "escalated": escalate, "vlm": None}
        if stage1_error:
            result["stage1_error"] = stage1_error
        if escalate:
            try:
                result["vlm"] = stage2_vlm(img, declared_type)
                result["stage"] = "stage2"
            except Exception as e:
                result["vlm_error"] = str(e)

    top = max(result["observations"], key=lambda o: o["score"])
    final_label = (result["vlm"] or {}).get("label", top["label"])
    latency = round(time.time() - t0, 3)
    cost = VLM_COST if result.get("stage") == "stage2" else 0.0
    COST_LOG.append({"evidence_id": evidence_id, "stage": result["stage"],
                     "latency_s": latency, "est_cost_usd": cost})
    return {
        "evidence_id": evidence_id,
        "model_id": FINETUNED_MODEL or STAGE1_MODEL,
        "escalation_model_id": VLM_MODEL if result.get("stage") == "stage2" else None,
        "observations": result["observations"],
        "final_label": final_label,
        "vlm": result.get("vlm"),
        "matches_declared_element": (declared_type is None) or final_label == declared_type,
        "requires_review": True,          # every observation goes to a human
        "completion_certified": False,    # deliberate: AI never certifies
        "latency_s": latency,
        "est_cost_usd": cost,
    }


def cost_summary() -> dict:
    n = len(COST_LOG)
    esc = sum(1 for c in COST_LOG if c["stage"] == "stage2")
    total = sum(c["est_cost_usd"] for c in COST_LOG)
    return {
        "photos_processed": n,
        "escalation_rate": round(esc / n, 3) if n else 0.0,
        "avg_latency_s": round(sum(c["latency_s"] for c in COST_LOG) / n, 3) if n else 0.0,
        "est_total_cost_usd": round(total, 4),
        "est_cost_if_always_vlm_usd": round(n * VLM_COST, 4),
        "cache_hits": sum(1 for c in COST_LOG if c["stage"] == "cache"),
        "log": COST_LOG[-50:],
    }