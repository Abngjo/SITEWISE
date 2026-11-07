"""'Ask SITEWISE': grounded Q&A over the computed project state (owner: Dev C).

The LLM (Gemma 4 via HF Inference Providers) only sees numbers that SITEWISE computed.
Every number in its answer is checked against those figures; if any number can't be found,
the answer is blocked and the user is told to use the reports instead.
"""
from __future__ import annotations

import json
import os
import re

LLM_MODEL = os.getenv("SITEWISE_LLM_MODEL", "google/gemma-4-31B-it")
SMALL_INT_OK = 31  # counts/days like "3 doors" or "2 storeys" are allowed if <= this AND present in context

_NUM = re.compile(r"(?<![A-Za-z\-])\d[\d,]*(?:\.\d+)?")
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def _numbers(text: str) -> set[float]:
    out = set()
    for m in _NUM.findall(text.translate(_AR_DIGITS)):
        try:
            out.add(round(float(m.replace(",", "")), 2))
        except ValueError:
            pass
    return out


def _strip_ids(text: str) -> str:
    """Element / task / BOQ / certificate IDs and dates contain digits but aren't figures."""
    text = re.sub(r"\b(?:[A-Z]{1,4}-){1,2}[A-Z]{0,4}\d+[A-Z0-9-]*\b", " ", text)  # D-103, BOQ-DR-01, IPC-04, T-210
    text = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", " ", text)                           # 2026-11-07
    text = re.sub(r"\bL\d\b", " ", text)                                          # L1 / L2
    return text


def context(store, audit: dict, sched: dict, overview: dict) -> dict:
    els = []
    for eid, e in store.elements.items():
        rate = float(store.boq[e["boq_item_id"]]["contract_rate"])
        els.append({"id": eid, "name": e["name"], "type": e["type"], "floor": e["floor"],
                    "status": store.element_status(eid), "claimed_now": eid in store.claimed_ids(),
                    "boq": e["boq_item_id"], "qty": float(e["quantity"]), "unit": e["unit"],
                    "value_qar": round(float(e["quantity"]) * rate, 2), "task": e["task_id"]})
    return {
        "project": store.project.get("name"), "certificate": audit.get("certificate_no"),
        "currency": "QAR", "totals": audit["totals"],
        "boq_items": [{k: i[k] for k in ("boq_item_id", "description", "unit", "rate", "claimed_value_this_period",
                                          "supported_value_this_period", "discrepancy", "status",
                                          "claimed_without_evidence")} for i in audit["items"]],
        "elements": els,
        "schedule": {k: sched.get(k) for k in ("baseline_handover", "forecast_handover", "handover_delay_days",
                                               "delay_exposure_qar", "delay_damages_per_day_qar", "critical_path")},
        "tasks": [{k: t.get(k) for k in ("task_id", "name", "progress", "finish", "baseline_finish",
                                         "total_float_days", "critical")} for t in sched["tasks"]],
        "counts": overview.get("counts", {}),
        "flags": [{k: f.get(k) for k in ("type", "element_id", "message")} for f in store.safety][-20:],
        "possible_reuse": [{"evidence_id": v["evidence_id"], "element_id": v.get("element_id"),
                            "matches": v["duplicates"][0]["evidence_id"]}
                           for v in store.evidence.values() if v.get("duplicates")],
    }


def grounded(answer: str, ctx: dict) -> tuple[bool, list[float]]:
    allowed = _numbers(json.dumps(ctx, ensure_ascii=False))
    # percentages derived from two context numbers are common; allow integers 0-100 only if in context
    bad = [n for n in _numbers(_strip_ids(answer)) if n not in allowed]
    return (not bad), bad


def ask(question: str, ctx: dict, lang: str = "en") -> dict:
    if os.getenv("SITEWISE_DISABLE_MODELS") == "1":
        return {"answer": "Ask SITEWISE needs the language model (models are disabled in this environment).",
                "grounded": None, "model": None}
    from huggingface_hub import InferenceClient
    language = "Modern Standard Arabic" if lang == "ar" else "English"
    system = (
        "You are SITEWISE, an assistant for a construction project engineer in Qatar reviewing a contractor's "
        "payment claim. Answer ONLY from the JSON project data provided. Use figures exactly as they appear in the "
        "data (do not add, subtract, round or estimate new numbers). Refer to elements by their IDs (e.g. D-103). "
        "If the data doesn't answer the question, say so. Never say work is certified or that payment should be "
        "made; the engineer decides. Keep answers under 120 words. Use western digits. "
        f"Answer in {language}."
    )
    msgs = [{"role": "system", "content": system},
            {"role": "user", "content": f"PROJECT DATA:\n{json.dumps(ctx, ensure_ascii=False)}\n\nQUESTION: {question}"}]
    try:
        out = InferenceClient(token=os.getenv("HF_TOKEN")).chat_completion(model=LLM_MODEL, messages=msgs,
                                                                           max_tokens=400, temperature=0.1)
        text = (out.choices[0].message.content or "").strip()
    except Exception as e:
        return {"answer": f"The language model is unavailable right now ({type(e).__name__}).",
                "grounded": None, "model": LLM_MODEL}
    ok, bad = grounded(text, ctx)
    if not ok:
        return {"answer": ("I couldn't verify every figure in my answer against the project data, so I'm not "
                           "showing it. Please check the Payment and Schedule pages."),
                "grounded": False, "blocked_figures": bad, "model": LLM_MODEL}
    return {"answer": text, "grounded": True, "model": LLM_MODEL}
