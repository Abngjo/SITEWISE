"""Payment audit engine (owner: Dev C).

Pure functions, deterministic. NO model calls here: money is computed by code only.

Definitions (per BOQ item, cumulative to date):
  supported_qty_cum   = sum of engineer-supported quantities of the item's elements
  claimed_this_period = max(0, claimed_qty_cumulative - previous_certified_qty) * rate
  supported_this_period = max(0, supported_qty_cum - previous_certified_qty) * rate
  discrepancy         = max(0, claimed_this_period - supported_this_period)

AI observations never count as supported; only engineer reviews with decision
"supported" (or "partial" with supported_qty) do.
"""
from __future__ import annotations


def element_supported_qty(element: dict, review: dict | None) -> float:
    if not review:
        return 0.0
    if review["decision"] == "supported":
        q = review.get("supported_qty")
        return float(q) if q not in (None, "") else float(element["quantity"])
    if review["decision"] == "partial":
        return float(review.get("supported_qty") or 0)
    return 0.0


def audit(boq: dict[str, dict], elements: dict[str, dict], reviews: dict[str, dict],
          claims: list[dict], retention_pct: float = 0.0) -> dict:
    items = []
    tot_claimed = tot_supported = tot_disc = 0.0
    for c in claims:
        item = boq[c["boq_item_id"]]
        rate = float(item["contract_rate"])
        prev = float(c["previous_certified_qty"])
        claimed_cum = float(c["claimed_qty_cumulative"])
        item_elements = [e for e in elements.values() if e["boq_item_id"] == c["boq_item_id"]]
        supported_cum = sum(element_supported_qty(e, reviews.get(e["element_id"])) for e in item_elements)
        claimed_val = max(0.0, claimed_cum - prev) * rate
        supported_val = max(0.0, supported_cum - prev) * rate
        disc = max(0.0, claimed_val - supported_val)

        claimed_ids = [x for x in str(c.get("claimed_element_ids") or "").split(";") if x]
        no_evidence = [eid for eid in claimed_ids
                       if eid in elements and reviews.get(eid) is None]
        status = ("supported" if disc == 0 else
                  "partially_supported" if supported_val > 0 else
                  "insufficient_evidence")
        items.append({
            "boq_item_id": c["boq_item_id"],
            "description": item["description"],
            "description_ar": item.get("description_ar", ""),
            "unit": item["unit"],
            "rate": rate,
            "previous_certified_qty": prev,
            "claimed_qty_cumulative": claimed_cum,
            "supported_qty_cumulative": supported_cum,
            "claimed_value_this_period": round(claimed_val, 2),
            "supported_value_this_period": round(supported_val, 2),
            "discrepancy": round(disc, 2),
            "status": status,
            "claimed_without_evidence": no_evidence,
        })
        tot_claimed += claimed_val
        tot_supported += supported_val
        tot_disc += disc

    retention = tot_supported * retention_pct / 100.0
    claimed_ids_all = {x for c in claims for x in str(c.get("claimed_element_ids") or "").split(";") if x}
    uncovered_value = sum(
        float(elements[e]["quantity"]) * float(boq[elements[e]["boq_item_id"]]["contract_rate"])
        for e in claimed_ids_all if e in elements and reviews.get(e) is None)
    return {
        "certificate_no": claims[0]["certificate_no"] if claims else None,
        "items": items,
        "totals": {
            "claimed_this_period": round(tot_claimed, 2),
            "supported_this_period": round(tot_supported, 2),
            "discrepancy": round(tot_disc, 2),
            "retention": round(retention, 2),
            "recommended_for_review_net": round(tot_supported - retention, 2),
            "claimed_value_with_no_evidence": round(uncovered_value, 2),
        },
        "note": "Recommendation only. Certification remains with the qualified engineer / QS.",
    }


def element_risk(boq: dict[str, dict], elements: dict[str, dict], reviews: dict[str, dict],
                 claims: list[dict]) -> dict:
    """Money at risk per element, for the 3D heat view.
    Each BOQ item's discrepancy (from audit()) is spread over the elements claimed under it, in
    proportion to each element's unsupported value. So the per-element figures add up exactly to
    the audit's total discrepancy; the 3D view never shows a number the audit doesn't."""
    a = audit(boq, elements, reviews, claims)
    out = {}
    for it, c in zip(a["items"], claims):
        rate = it["rate"]
        ids = [x for x in str(c.get("claimed_element_ids") or "").split(";") if x in elements]
        gaps = {e: max(0.0, float(elements[e]["quantity"]) - element_supported_qty(elements[e], reviews.get(e))) * rate
                for e in ids}
        total_gap = sum(gaps.values())
        for e, g in gaps.items():
            share = it["discrepancy"] * g / total_gap if total_gap else 0.0
            out[e] = {"at_risk": round(share, 2), "claimed_value": round(float(elements[e]["quantity"]) * rate, 2),
                      "boq_item_id": it["boq_item_id"]}
    total = round(sum(v["at_risk"] for v in out.values()), 2)
    return {"elements": out, "total_at_risk": total, "audit_discrepancy": a["totals"]["discrepancy"],
            "max_at_risk": max([v["at_risk"] for v in out.values()] or [0])}
