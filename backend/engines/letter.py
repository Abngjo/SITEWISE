"""Audit letter to the contractor (owner: Dev C).

Structure:
  header            -> code
  opening paragraph -> open LLM via HF Inference Providers (optional), NO NUMBERS ALLOWED
  itemised findings -> code templates (EN/AR), every figure from the payment engine
  closing           -> code
If the LLM is unavailable, or its paragraph contains any digit, a fixed template is used.
"""
from __future__ import annotations

import os
import re

LLM_MODEL = os.getenv("SITEWISE_LLM_MODEL", "google/gemma-4-31B-it")


def qar(x: float) -> str:
    return f"QAR {x:,.0f}"


def findings(store, audit: dict) -> list[dict]:
    """Deterministic list of issues the contractor must address."""
    out = []
    els, boq = store.elements, store.boq
    # 1. claimed elements with no evidence at all
    for item in audit["items"]:
        for eid in item["claimed_without_evidence"]:
            e = els[eid]
            val = float(e["quantity"]) * float(boq[e["boq_item_id"]]["contract_rate"])
            out.append({"type": "no_evidence", "element_id": eid, "boq_item_id": e["boq_item_id"],
                        "value": val, "name": e["name"], "name_ar": e.get("name_ar", e["name"])})
    # 2. evidence from this certificate that matches earlier photos, or AI says incomplete
    for ev in store.evidence.values():
        if ev.get("prior") or not ev.get("element_id"):
            continue
        e = els[ev["element_id"]]
        if ev.get("duplicates"):
            d = ev["duplicates"][0]
            out.append({"type": "possible_reuse", "element_id": e["element_id"], "evidence_id": ev["evidence_id"],
                        "earlier_evidence_id": d["evidence_id"], "earlier_certificate": d.get("certificate_no"),
                        "name": e["name"], "name_ar": e.get("name_ar", e["name"])})
        comp = (ev.get("ai") or {}).get("completion")
        review = store.reviews.get(e["element_id"])
        if comp in ("partial", "not_started") and not (review and review["decision"] == "supported"):
            out.append({"type": "possibly_incomplete", "element_id": e["element_id"],
                        "evidence_id": ev["evidence_id"], "completion": comp,
                        "reason": ((ev.get("ai") or {}).get("vlm") or {}).get("reason", ""),
                        "name": e["name"], "name_ar": e.get("name_ar", e["name"])})
    # 3. engineer-rejected / partial items
    for eid, r in store.reviews.items():
        if r["decision"] in ("rejected", "partial") and eid in store.claimed_ids():
            e = els[eid]
            out.append({"type": f"engineer_{r['decision']}", "element_id": eid, "reason": r.get("reason", ""),
                        "name": e["name"], "name_ar": e.get("name_ar", e["name"])})
    return out


EN = {
    "no_evidence": lambda f: f"{f['element_id']} ({f['name']}): claimed under {f['boq_item_id']} "
                             f"({qar(f['value'])}) with no photographic evidence. Please submit current, dated photos.",
    "possible_reuse": lambda f: f"{f['element_id']} ({f['name']}): photo {f['evidence_id']} closely matches "
                                f"{f['earlier_evidence_id']} submitted with {f['earlier_certificate']}. Please provide a current photo.",
    "possibly_incomplete": lambda f: f"{f['element_id']} ({f['name']}): the submitted photo suggests the work may be "
                                     f"{f['completion'].replace('_', ' ')}. Please confirm the status or adjust the claimed quantity.",
    "engineer_rejected": lambda f: f"{f['element_id']} ({f['name']}): not accepted by the site engineer ({f['reason']}).",
    "engineer_partial": lambda f: f"{f['element_id']} ({f['name']}): partially accepted by the site engineer ({f['reason']}).",
}
AR = {
    "no_evidence": lambda f: f"{f['element_id']} ({f['name_ar']}): مطالب به ضمن البند {f['boq_item_id']} "
                             f"بقيمة {qar(f['value'])} دون أي دليل مصور. يرجى تقديم صور حديثة مؤرخة.",
    "possible_reuse": lambda f: f"{f['element_id']} ({f['name_ar']}): الصورة {f['evidence_id']} تتطابق بدرجة كبيرة مع "
                                f"الصورة {f['earlier_evidence_id']} المقدمة مع الشهادة {f['earlier_certificate']}. يرجى تقديم صورة حديثة.",
    "possibly_incomplete": lambda f: f"{f['element_id']} ({f['name_ar']}): تشير الصورة المقدمة إلى أن العمل قد يكون غير مكتمل. "
                                     "يرجى تأكيد الحالة أو تعديل الكمية المطالب بها.",
    "engineer_rejected": lambda f: f"{f['element_id']} ({f['name_ar']}): لم يقبله مهندس الموقع ({f['reason']}).",
    "engineer_partial": lambda f: f"{f['element_id']} ({f['name_ar']}): قبله مهندس الموقع جزئياً ({f['reason']}).",
}

FALLBACK_OPENING = {
    "en": ("Following our review of the interim payment application, we have identified items where the "
           "submitted evidence does not yet support the claimed progress. We kindly request the information "
           "below so that the assessment can be completed."),
    "ar": ("بعد مراجعة طلب الدفعة المرحلية، تبيّن وجود بنود لا تدعم فيها الأدلة المقدمة التقدم المطالب به حتى الآن. "
           "نرجو تزويدنا بالمعلومات أدناه لاستكمال التقييم."),
}


def _llm_opening(lang: str, n_findings: int, types: list[str]) -> tuple[str, str]:
    if os.getenv("SITEWISE_DISABLE_MODELS") == "1":
        return FALLBACK_OPENING[lang], "template"
    try:
        from huggingface_hub import InferenceClient
        language = "formal Modern Standard Arabic" if lang == "ar" else "formal British English"
        prompt = (f"Write ONE short, polite, professional opening paragraph (max 60 words) in {language} for a "
                  "letter from a project owner's engineer to a building contractor about their monthly payment "
                  f"application. The review found issues of these kinds: {', '.join(sorted(set(types)))}. "
                  "Do NOT include any numbers, amounts, dates, names or element IDs. Do not accuse anyone of fraud. "
                  "Return only the paragraph.")
        out = InferenceClient(token=os.getenv("HF_TOKEN")).chat_completion(
            model=LLM_MODEL, messages=[{"role": "user", "content": prompt}], max_tokens=200)
        text = out.choices[0].message.content.strip()
        if re.search(r"[0-9٠-٩]", text) or len(text) < 20:  # guard: the LLM must not produce figures
            return FALLBACK_OPENING[lang], "template (llm output rejected)"
        return text, LLM_MODEL
    except Exception:
        return FALLBACK_OPENING[lang], "template (llm unavailable)"


def build(store, audit: dict, lang: str = "en") -> dict:
    fs = findings(store, audit)
    t = audit["totals"]
    p = store.project
    opening, source = _llm_opening(lang, len(fs), [f["type"] for f in fs])
    tpl = AR if lang == "ar" else EN
    items = [tpl[f["type"]](f) for f in fs if f["type"] in tpl]
    if lang == "ar":
        header = [f"إلى: {p['contractor']}", f"المشروع: {p.get('name_ar', p['name'])}",
                  f"الموضوع: مراجعة شهادة الدفع {audit['certificate_no']}"]
        summary = (f"القيمة المطالب بها لهذه الفترة {qar(t['claimed_this_period'])}، والقيمة المدعومة بأدلة "
                   f"مراجَعة {qar(t['supported_this_period'])}، والفرق قيد المراجعة {qar(t['discrepancy'])}.")
        closing = "يرجى تقديم المعلومات المطلوبة قبل الموعد النهائي للتقييم. هذه مسودة للمراجعة من قبل المهندس المختص. بيانات تجريبية."
    else:
        header = [f"To: {p['contractor']}", f"Project: {p['name']}",
                  f"Subject: Review of payment application {audit['certificate_no']}"]
        summary = (f"Claimed this period: {qar(t['claimed_this_period'])}. Supported by reviewed evidence: "
                   f"{qar(t['supported_this_period'])}. Amount under review: {qar(t['discrepancy'])}.")
        closing = ("Please provide the requested information before the assessment deadline. "
                   "Draft for review and signature by the responsible engineer. Sample data.")
    return {"lang": lang, "direction": "rtl" if lang == "ar" else "ltr",
            "header": header, "opening": opening, "opening_source": source,
            "summary": summary, "items": items, "closing": closing,
            "findings": fs, "figures": t}