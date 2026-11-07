"""BIM (IFC) engine (owner: Dev C).

Parses the IFC file with IfcOpenShell at runtime so BIM is a real input, not a picture:
  - schema, project, storeys, element counts per IFC class
  - per element: GlobalId, IFC class, Tag (= SITEWISE element_id), storey
  - mapping check against SITEWISE records (BOQ item + schedule task per element)
POST /api/bim/import lets a user upload an IFC and see this mapping report.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

BUILDING_CLASSES = ("IfcWall", "IfcSlab", "IfcDoor", "IfcCovering", "IfcWindow", "IfcColumn", "IfcBeam")


def _storey_of(el) -> str | None:
    for rel in getattr(el, "ContainedInStructure", None) or []:
        st = rel.RelatingStructure
        if st.is_a("IfcBuildingStorey"):
            return st.Name
    return None


def parse(ifc_path: str | Path, elements: dict[str, dict]) -> dict:
    import ifcopenshell  # imported lazily so the API still boots if it's missing
    f = ifcopenshell.open(str(ifc_path))
    project = (f.by_type("IfcProject") or [None])[0]
    storeys = sorted(((s.Name, float(s.Elevation or 0)) for s in f.by_type("IfcBuildingStorey")),
                     key=lambda x: x[1])
    rows, counts = [], Counter()
    for cls in BUILDING_CLASSES:
        for el in f.by_type(cls):
            counts[cls] += 1
            eid = el.Tag or None
            rec = elements.get(eid) if eid else None
            rows.append({
                "ifc_guid": el.GlobalId, "ifc_class": el.is_a(), "name": el.Name,
                "element_id": eid, "storey": _storey_of(el),
                "mapped": rec is not None,
                "boq_item_id": rec["boq_item_id"] if rec else None,
                "task_id": rec["task_id"] if rec else None,
                "guid_matches_record": (rec is not None and rec.get("ifc_guid") in ("", None, el.GlobalId)),
            })
    ifc_ids = {r["element_id"] for r in rows if r["element_id"]}
    missing_in_ifc = sorted(set(elements) - ifc_ids)
    unmapped = [r for r in rows if not r["mapped"]]
    return {
        "schema": f.schema,
        "project": project.Name if project else None,
        "storeys": [{"name": n, "elevation_m": e} for n, e in storeys],
        "element_counts": dict(counts),
        "total_elements": len(rows),
        "mapped_elements": len(rows) - len(unmapped),
        "unmapped_ifc_elements": unmapped,
        "sitewise_records_missing_in_ifc": missing_in_ifc,
        "elements": rows,
    }


def export_as_verified(ifc_path: str | Path, out_path: str | Path, store, audit: dict) -> Path:
    """Write SITEWISE evidence status back into the BIM as an IfcPropertySet on every element.
    The result opens in any IFC viewer (e.g. BIMvision, Solibri, BlenderBIM) under 'SITEWISE_Evidence'."""
    import ifcopenshell
    import ifcopenshell.api.pset
    from .payment import element_supported_qty
    f = ifcopenshell.open(str(ifc_path))
    claimed = store.claimed_ids()
    cert = store.project.get("current_certificate", "")
    for el in f.by_type("IfcElement"):
        eid = el.Tag
        rec = store.elements.get(eid) if eid else None
        if not rec:
            continue
        review = store.reviews.get(eid)
        rate = float(store.boq[rec["boq_item_id"]]["contract_rate"])
        sup_qty = element_supported_qty(rec, review)
        ev_ids = [k for k, v in store.evidence.items() if v.get("element_id") == eid]
        pset = ifcopenshell.api.pset.add_pset(f, product=el, name="SITEWISE_Evidence")
        ifcopenshell.api.pset.edit_pset(f, pset=pset, properties={
            "Certificate": cert,
            "EvidenceStatus": store.element_status(eid),
            "ClaimedThisCertificate": eid in claimed,
            "BOQItem": rec["boq_item_id"],
            "ContractRateQAR": rate,
            "Quantity": float(rec["quantity"]),
            "Unit": rec["unit"],
            "SupportedQuantity": float(sup_qty),
            "SupportedValueQAR": round(float(sup_qty) * rate, 2),
            "ScheduleTask": rec["task_id"],
            "ReviewDecision": review["decision"] if review else "not_reviewed",
            "Reviewer": (review or {}).get("reviewer") or "",
            "EvidenceIds": ";".join(ev_ids),
            "Note": "AI observations only; certification by the responsible engineer. Sample data.",
        })
    f.write(str(out_path))
    return Path(out_path)
