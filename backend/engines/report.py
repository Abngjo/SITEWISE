"""Bilingual audit summary (owner: Dev C).

RULE: every number is inserted by code from the payment/schedule results.
If an LLM is later used to polish wording, it must only fill text around
{placeholders}; never let it generate or restate figures.
"""
from __future__ import annotations


def qar(x: float) -> str:
    return f"QAR {x:,.0f}"


def build(project: dict, audit: dict, sched: dict, safety: list[dict], dup_flags: list[dict],
          costs: dict, lang: str = "en") -> dict:
    t = audit["totals"]
    n_disc = sum(1 for i in audit["items"] if i["discrepancy"] > 0)
    d = sched["handover_delay_days"]
    if lang == "ar":
        lines = [
            f"المشروع: {project.get('name_ar', project['name'])}",
            f"شهادة الدفع: {audit['certificate_no']} — تاريخ التدقيق: {sched['as_of']}",
            f"القيمة المطالب بها لهذه الفترة: {qar(t['claimed_this_period'])}",
            f"القيمة المدعومة بأدلة مراجَعة: {qar(t['supported_this_period'])}",
            f"الفرق الذي يتطلب مراجعة: {qar(t['discrepancy'])} في {n_disc} بنود",
            f"قيمة مطالب بها دون أي دليل مصور: {qar(t['claimed_value_with_no_evidence'])}",
            f"صور يُحتمل إعادة استخدامها من شهادات سابقة: {len(dup_flags)}",
            f"ملاحظات السلامة والامتثال بانتظار المراجعة: {len(safety)}",
            f"موعد التسليم المتوقع: {sched['forecast_handover']} (التأخير مقارنة بالخطة الأساسية: {d} يوم)",
            f"التعرض المقدر لغرامات التأخير: {qar(sched.get('delay_exposure_qar', 0))} (افتراض تجريبي)",
            f"تكلفة معالجة الذكاء الاصطناعي التقديرية: {costs['est_total_cost_usd']} دولار لعدد {costs['photos_processed']} صورة",
            "هذا التقرير توصية فقط، ويبقى قرار الاعتماد للمهندس أو مساح الكميات المختص. بيانات تجريبية.",
        ]
    else:
        lines = [
            f"Project: {project['name']}",
            f"Payment certificate: {audit['certificate_no']} | Audit date: {sched['as_of']}",
            f"Claimed this period: {qar(t['claimed_this_period'])}",
            f"Supported by reviewed evidence: {qar(t['supported_this_period'])}",
            f"Discrepancy requiring review: {qar(t['discrepancy'])} across {n_disc} BOQ items",
            f"Claimed value with no photo evidence: {qar(t['claimed_value_with_no_evidence'])}",
            f"Possible reused photos from earlier certificates: {len(dup_flags)}",
            f"Safety and compliance flags awaiting review: {len(safety)}",
            f"Forecast handover: {sched['forecast_handover']} (variance vs baseline: {d} days)",
            f"Estimated delay damages exposure: {qar(sched.get('delay_exposure_qar', 0))} (sample assumption)",
            f"Estimated AI processing cost: ${costs['est_total_cost_usd']} for {costs['photos_processed']} photos",
            "Recommendation only. Certification remains with the qualified engineer / QS. Sample data.",
        ]
    return {"lang": lang, "direction": "rtl" if lang == "ar" else "ltr", "lines": lines,
            "figures": {**t, "handover_delay_days": d, "delay_exposure_qar": sched.get("delay_exposure_qar", 0)}}
