"""Two-stage image analysis router (owner: Dev A).

Stage 1: small model inside the Space (SigLIP2 zero-shot, or your fine-tuned checkpoint).
Stage 2: only if stage 1 is uncertain or disagrees with the declared element ->
         Gemma 4 31B, then Qwen2.5-VL-72B only if Gemma is unusable.
Output is an OBSERVATION. `completion_certified` is always False.

Env vars:
  HF_TOKEN                   token (Space secret / local .env)
  SITEWISE_STAGE1_MODEL      default google/siglip2-base-patch16-224 (zero-shot)
  SITEWISE_FINETUNED_MODEL   e.g. mfjbrr/team-QH045-sitewise (image-classification head); overrides zero-shot
  SITEWISE_VLM_MODEL         default google/gemma-4-31B-it (verified via Inference Providers)
  SITEWISE_VLM_FALLBACK      default Qwen/Qwen2.5-VL-72B-Instruct (used if the primary call fails)
  SITEWISE_ESCALATION_THRESHOLD  default 0.80 (calibrate on your eval set!)
  SITEWISE_VLM_COST_USD      estimated cost per escalated call, for the cost log (replace with real numbers)
  SITEWISE_DISABLE_MODELS=1  return stub predictions (for frontend/backend dev without models)
"""
from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import os
import re
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
VLM_MODEL = os.getenv("SITEWISE_VLM_MODEL", "google/gemma-4-31B-it")
VLM_FALLBACK = os.getenv("SITEWISE_VLM_FALLBACK", "Qwen/Qwen2.5-VL-72B-Instruct")
THRESHOLD = float(os.getenv("SITEWISE_ESCALATION_THRESHOLD", "0.80"))
VLM_COST = float(os.getenv("SITEWISE_VLM_COST_USD", "0.002"))
DISABLED = os.getenv("SITEWISE_DISABLE_MODELS") == "1"

_pipe = None
COST_LOG: list[dict] = []


class VLMCallError(RuntimeError):
    """Internal error retaining metering for failed provider attempts."""

    def __init__(self, message: str, calls: list[dict], fallback_reasons: list[str]):
        super().__init__(message)
        self.calls = calls
        self.fallback_reasons = fallback_reasons


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
    # SigLIP scores each label independently (sigmoid), so raw scores don't sum to 1
    # (e.g. door=0.21, others ~0). Normalise across our 4 labels so the escalation
    # threshold means "share of belief", and keep the raw score for transparency.
    total = sum(float(r["score"]) for r in res) or 1.0
    return [{"label": inv[r["label"]], "score": float(r["score"]) / total,
             "raw_score": float(r["score"])} for r in res]


def _usage_value(usage, name: str):
    return usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)


def _extract_json_object(text: str) -> dict:
    """Extract the first JSON object from plain, fenced, or surrounding text."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("empty response")
    stripped = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped,
                          flags=re.DOTALL | re.IGNORECASE)
    candidate = fenced.group(1) if fenced else stripped
    decoder = json.JSONDecoder()
    for position, character in enumerate(candidate):
        if character != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(candidate[position:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("response contains no valid JSON object")


def _validate_vlm_response(parsed: dict) -> dict:
    if parsed.get("label") not in LABELS:
        raise ValueError("invalid or missing label")
    if parsed.get("completion") not in ("complete", "partial", "not_started", "unclear"):
        raise ValueError("invalid or missing completion")
    if not isinstance(parsed.get("reason"), str) or not parsed["reason"].strip():
        raise ValueError("missing reason")
    return parsed


def stage2_vlm(img: Image.Image, declared_type: str | None, claimed_complete: bool = False) -> dict:
    from huggingface_hub import InferenceClient
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=85)
    url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    prompt = (
        "You are assisting a construction site engineer. Look at the photo and answer ONLY with JSON: "
        '{"label": one of ["door","wall","ceiling","other"], '
        '"completion": one of ["complete","partial","not_started","unclear"], '
        '"reason": "<one short sentence>"}. '
        f"The contractor says this photo shows a {declared_type or 'construction element'}"
        + (" and claims the work is COMPLETE (fully installed, ready to pay). Judge strictly whether the "
           "installation visible in the photo is complete; e.g. a door frame without the door leaf is "
           "partial, a ceiling grid without boards is partial." if claimed_complete else ".")
    )
    client = InferenceClient(token=os.getenv("HF_TOKEN"))
    msgs = [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": url}},
        {"type": "text", "text": prompt}]}]
    last_err = None
    calls = []
    fallback_reasons = []
    res = None
    for model in (VLM_MODEL, VLM_FALLBACK):
        started = time.perf_counter()
        call = {
            "model": model, "latency_s": 0.0,
            "input_tokens": None, "output_tokens": None,
            "estimated_cost_usd": VLM_COST,
            "provider_reported_cost_usd": None,
            "provider_confirmed_cost_usd": None,
            "cost_source": "estimated", "error": None,
        }
        calls.append(call)
        try:
            out = client.chat_completion(model=model, messages=msgs, max_tokens=300)
            call["latency_s"] = time.perf_counter() - started
            usage = getattr(out, "usage", None)
            if usage is not None:
                input_tokens = _usage_value(usage, "prompt_tokens")
                output_tokens = _usage_value(usage, "completion_tokens")
                provider_cost = _usage_value(usage, "estimated_cost")
                confirmed_cost = _usage_value(usage, "actual_cost_usd")
                if type(input_tokens) is int and input_tokens >= 0:
                    call["input_tokens"] = input_tokens
                if type(output_tokens) is int and output_tokens >= 0:
                    call["output_tokens"] = output_tokens
                if type(provider_cost) in (int, float) and provider_cost >= 0:
                    call["provider_reported_cost_usd"] = float(provider_cost)
                    call["estimated_cost_usd"] = float(provider_cost)
                    call["cost_source"] = "provider_reported_estimate"
                if type(confirmed_cost) in (int, float) and confirmed_cost >= 0:
                    call["provider_confirmed_cost_usd"] = float(confirmed_cost)
                    call["cost_source"] = "provider_confirmed"
            if not getattr(out, "choices", None):
                raise ValueError("response contains no choices")
            if getattr(out.choices[0], "finish_reason", None) == "length":
                raise ValueError("response was truncated")
            text = out.choices[0].message.content
            res = _validate_vlm_response(_extract_json_object(text))
            break
        except Exception as e:
            last_err = e
            call["latency_s"] = time.perf_counter() - started
            call["error"] = str(e)
            fallback_reasons.append(f"{model}:{type(e).__name__}:{e}")
    else:
        raise VLMCallError(f"all VLMs failed: {last_err}", calls, fallback_reasons)
    res["model"] = model
    # Private metering is removed before the public response is assembled.
    res["_metering"] = {
        "calls": calls, "fallback_reasons": fallback_reasons,
        "valid_response": True,
    }
    return res


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
        # Transformers versions may return either the feature tensor directly
        # or a BaseModelOutputWithPooling wrapper for SigLIP2.
        if getattr(f, "image_embeds", None) is not None:
            f = f.image_embeds
        elif getattr(f, "pooler_output", None) is not None:
            f = f.pooler_output
        f = f / f.norm(dim=-1, keepdim=True)
        return [round(float(x), 5) for x in f[0]]
    except Exception:
        return None


def analyze(image_bytes: bytes, evidence_id: str, declared_type: str | None,
            claimed_complete: bool = False) -> dict:
    """claimed_complete=True: the contractor claims this element is finished in the current
    certificate, so the VLM is always asked to judge completion (not just what the photo shows)."""
    key = hashlib.sha256(image_bytes).hexdigest() + f":{declared_type}:{claimed_complete}"
    if key in _CACHE:  # identical photo already analysed: reuse result, zero cost
        started = time.perf_counter()
        cached = _CACHE[key]
        hit = copy.deepcopy(cached["response"])
        hit.update(evidence_id=evidence_id, est_cost_usd=0.0, cache_hit=True)
        cache_latency = time.perf_counter() - started
        hit["latency_s"] = round(cache_latency, 3)
        COST_LOG.append({
            "evidence_id": evidence_id, "stage": "cache", "latency_s": cache_latency,
            "siglip_latency_s": 0.0, "vlm_latency_s": 0.0,
            "est_cost_usd": 0.0, "estimated_cost_usd": 0.0,
            "provider_confirmed_cost_usd": 0.0, "provider_billing_fully_confirmed": False,
            "total_cost_usd": 0.0, "cost_source": "cache",
            "models_called": [], "models_reused": cached["models_reused"],
            "input_tokens": 0, "output_tokens": 0, "calls": [],
            "escalated": cached["escalated"], "escalation_reason": "identical_image_cache_hit",
            "fallback_reasons": [], "cache_hit": True, "successful": True,
            "avoided_provider_cost_usd": cached["avoided_provider_cost_usd"],
        })
        return hit
    res = _analyze(image_bytes, evidence_id, declared_type, claimed_complete)
    cacheable = res.pop("_cacheable")
    avoided_cost = res.pop("_cache_avoided_provider_cost_usd")
    models_reused = res.pop("_models_reused")
    escalated = res.pop("_escalated")
    if cacheable:
        _CACHE[key] = {
            "response": copy.deepcopy(res),
            "avoided_provider_cost_usd": avoided_cost,
            "models_reused": models_reused,
            "escalated": escalated,
        }
    return res


def _analyze(image_bytes: bytes, evidence_id: str, declared_type: str | None,
             claimed_complete: bool = False) -> dict:
    t0 = time.perf_counter()
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img.thumbnail((768, 768))  # cost/latency: no need for full resolution
    stage1_latency = 0.0
    calls = []
    fallback_reasons = []
    valid_vlm_response = True

    if DISABLED:
        obs = [{"label": declared_type or "other", "score": 0.5}]
        result = {"stage": "stub", "observations": obs, "escalated": False, "vlm": None}
    else:
        stage1_error = None
        stage1_started = time.perf_counter()
        try:
            obs = stage1(img)
            if ({item.get("label") for item in obs} != set(LABELS)
                    or any(type(item.get("score")) not in (int, float) for item in obs)):
                raise ValueError("stage 1 returned incomplete observations")
        except Exception as e:  # model failed to load -> graceful review-needed state
            obs = [{"label": "other", "score": 0.0}]
            stage1_error = str(e)
        stage1_latency = time.perf_counter() - stage1_started
        top = max(obs, key=lambda o: o["score"])
        mismatch = declared_type is not None and top["label"] != declared_type
        escalate = top["score"] < THRESHOLD or mismatch or claimed_complete
        reason = ("completion_check" if claimed_complete else
                  "label_mismatch" if mismatch else
                  "low_confidence" if top["score"] < THRESHOLD else None)
        result = {"stage": "stage1", "observations": obs, "escalated": escalate, "vlm": None,
                  "escalation_reason": reason}
        if stage1_error:
            result["stage1_error"] = stage1_error
        if escalate:
            try:
                vlm = stage2_vlm(img, declared_type, claimed_complete)
                metering = vlm.pop("_metering", {})
                calls = metering.get("calls", [])
                fallback_reasons = metering.get("fallback_reasons", [])
                valid_vlm_response = bool(metering.get("valid_response", False))
                result["vlm"] = vlm
                result["stage"] = "stage2"
            except VLMCallError as e:
                calls = e.calls
                fallback_reasons = e.fallback_reasons
                result["vlm_error"] = str(e)
            except Exception as e:
                fallback_reasons.append(f"unmetered:{type(e).__name__}")
                result["vlm_error"] = str(e)

    top = max(result["observations"], key=lambda o: o["score"])
    final_label = (result["vlm"] or {}).get("label", top["label"])
    latency = time.perf_counter() - t0
    vlm_latency = sum(float(call.get("latency_s") or 0) for call in calls)
    confirmed = [call.get("provider_confirmed_cost_usd") for call in calls]
    confirmed_total = sum(float(value) for value in confirmed if value is not None)
    estimated_total = sum(float(call.get("estimated_cost_usd") or 0) for call in calls
                          if call.get("provider_confirmed_cost_usd") is None)
    total_cost = confirmed_total + estimated_total
    billing_confirmed = bool(calls) and all(value is not None for value in confirmed)

    def token_total(name: str):
        if not calls:
            return 0
        values = [call.get(name) for call in calls]
        return sum(values) if all(type(value) is int for value in values) else None

    models_called = ([] if DISABLED else [FINETUNED_MODEL or STAGE1_MODEL])
    models_called += [call["model"] for call in calls]
    escalated = bool(result.get("escalated"))
    successful = (not result.get("stage1_error") and not result.get("vlm_error")
                  and (not escalated or (result.get("stage") == "stage2" and valid_vlm_response)))
    cost_source = ("local" if not calls else "provider_confirmed" if billing_confirmed else
                   "mixed" if confirmed_total else "estimated")
    record = {
        "evidence_id": evidence_id, "stage": result["stage"], "latency_s": latency,
        "siglip_latency_s": stage1_latency, "vlm_latency_s": vlm_latency,
        "est_cost_usd": total_cost, "estimated_cost_usd": estimated_total,
        "provider_confirmed_cost_usd": confirmed_total,
        "provider_billing_fully_confirmed": billing_confirmed,
        "total_cost_usd": total_cost, "cost_source": cost_source,
        "models_called": models_called, "models_reused": [],
        "input_tokens": token_total("input_tokens"),
        "output_tokens": token_total("output_tokens"),
        "calls": calls, "escalated": escalated,
        "escalation_reason": result.get("escalation_reason"),
        "fallback_reasons": fallback_reasons, "cache_hit": False,
        "successful": successful, "avoided_provider_cost_usd": 0.0,
    }
    COST_LOG.append(record)
    response = {
        "evidence_id": evidence_id,
        "model_id": FINETUNED_MODEL or STAGE1_MODEL,
        "escalation_model_id": (result.get("vlm") or {}).get("model") if result.get("stage") == "stage2" else None,
        "observations": result["observations"],
        "final_label": final_label,
        "vlm": result.get("vlm"),
        "matches_declared_element": (declared_type is None) or final_label == declared_type,
        "claimed_complete": claimed_complete,
        "escalation_reason": result.get("escalation_reason"),
        "vlm_error": result.get("vlm_error"),        # set if escalation was needed but the VLM call failed
        "stage1_error": result.get("stage1_error"),
        # complete | partial | not_started | unclear | None (no VLM call)
        "completion": (result.get("vlm") or {}).get("completion"),
        "requires_review": True,          # every observation goes to a human
        "completion_certified": False,    # deliberate: AI never certifies
        "latency_s": round(latency, 3),
        "est_cost_usd": total_cost,
    }
    response["_cacheable"] = bool(successful)
    response["_cache_avoided_provider_cost_usd"] = total_cost if escalated else 0.0
    response["_models_reused"] = models_called
    response["_escalated"] = escalated
    return response


def cost_summary() -> dict:
    n = len(COST_LOG)
    esc = sum(bool(c.get("escalated", c["stage"] == "stage2")) for c in COST_LOG)
    total = sum(float(c.get("total_cost_usd", c["est_cost_usd"])) for c in COST_LOG)
    estimated = sum(float(c.get("estimated_cost_usd", c["est_cost_usd"])) for c in COST_LOG)
    confirmed = sum(float(c.get("provider_confirmed_cost_usd", 0.0)) for c in COST_LOG)
    always_vlm = n * VLM_COST
    avoided = sum(float(c.get("avoided_provider_cost_usd", 0.0)) for c in COST_LOG)
    return {
        "photos_processed": n,
        "escalation_rate": round(esc / n, 3) if n else 0.0,
        "avg_latency_s": round(sum(c["latency_s"] for c in COST_LOG) / n, 3) if n else 0.0,
        "est_total_cost_usd": round(total, 8),
        "est_cost_if_always_vlm_usd": round(always_vlm, 8),
        "cache_hits": sum(1 for c in COST_LOG if c["stage"] == "cache"),
        "estimated_cost_usd": round(estimated, 8),
        "provider_confirmed_cost_usd": round(confirmed, 8),
        "total_cost_usd": round(total, 8),
        "avoided_provider_cost_usd": round(avoided, 8),
        "estimated_savings_vs_always_vlm_usd": round(always_vlm - total, 8),
        "log": COST_LOG[-50:],
    }
