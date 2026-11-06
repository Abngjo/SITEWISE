"""Project state (owner: Dev C).

Hackathon version: CSV sample data + in-memory state persisted to state.json.
Swap for SQLite later without changing the API (keep the same dict shapes).
"""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("SITEWISE_DATA_DIR", ROOT / "data" / "sample_project"))
STATE_FILE = Path(os.getenv("SITEWISE_STATE_FILE", ROOT / "data" / "state.json"))


def _csv(name: str) -> list[dict]:
    with open(DATA_DIR / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class Store:
    def __init__(self):
        self.reset()

    def reset(self):
        self.project = json.loads((DATA_DIR / "project.json").read_text(encoding="utf-8"))
        self.boq = {r["item_id"]: r for r in _csv("boq.csv")}
        self.elements = {r["element_id"]: r for r in _csv("elements.csv")}
        self.tasks = {}
        for r in _csv("schedule.csv"):
            r["predecessors"] = [p for p in r["predecessors"].split(";") if p]
            r["duration_days"] = float(r["duration_days"])
            self.tasks[r["task_id"]] = r
        self.claims = [c for c in _csv("claims.csv")
                       if c["certificate_no"] == self.project["current_certificate"]]
        self.reviews = {r["element_id"]: r for r in _csv("reviews_seed.csv")}
        self.evidence: dict[str, dict] = {}   # evidence_id -> record (no image bytes)
        self.safety: list[dict] = []
        if STATE_FILE.exists():
            s = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            self.reviews.update(s.get("reviews", {}))
            self.evidence.update(s.get("evidence", {}))
            self.safety = s.get("safety", [])

    def save(self):
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(
            {"reviews": self.reviews, "evidence": self.evidence, "safety": self.safety},
            ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- derived views -------------------------------------------------
    def claimed_ids(self) -> set[str]:
        return {x for c in self.claims for x in (c.get("claimed_element_ids") or "").split(";") if x}

    def element_status(self, eid: str) -> str:
        """green=supported, amber=uncertain, red=discrepancy, grey=no_evidence (plan legend)."""
        r = self.reviews.get(eid)
        has_evidence = any(e.get("element_id") == eid for e in self.evidence.values())
        if r:
            return {"supported": "supported", "partial": "uncertain", "uncertain": "uncertain",
                    "rejected": "discrepancy"}.get(r["decision"], "uncertain")
        if has_evidence:
            return "uncertain"
        if eid in self.claimed_ids():
            return "discrepancy"  # claimed this period with no evidence at all
        return "no_evidence"

    def task_progress(self) -> dict[str, float]:
        from .engines.payment import element_supported_qty
        prog = {}
        for tid, t in self.tasks.items():
            els = [e for e in self.elements.values() if e["task_id"] == tid]
            if not els:
                prog[tid] = float(t.get("manual_progress") or 0)
                continue
            tot = sup = 0.0
            for e in els:
                rate = float(self.boq[e["boq_item_id"]]["contract_rate"])
                tot += float(e["quantity"]) * rate
                sup += element_supported_qty(e, self.reviews.get(e["element_id"])) * rate
            prog[tid] = sup / tot if tot else 0.0
        return prog


store = Store()
