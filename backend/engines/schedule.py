"""Critical-path schedule engine with a Qatar working calendar (owner: Dev C).

Conventions
- Durations are in working days. Work week is Saturday-Thursday (Friday off).
- Each calendar day has a capacity in "work units": indoor = 1.0.
- Outdoor tasks during the summer midday restriction window get reduced capacity
  (SUMMER_OUTDOOR_CAPACITY). The plan's source rule: 1 June - 15 September,
  no outdoor work 10:00-15:30. VERIFY the current Ministry of Labour decision before
  any operational use. Indoor / properly ventilated work is NOT reduced.
- Finish-to-start dependencies. A task starts the calendar day after its latest
  predecessor finishes (or on the as-of date for forecasts).
"""
from __future__ import annotations

from datetime import date, timedelta

FRIDAY = 4  # date.weekday(): Mon=0 ... Fri=4
SUMMER_START = (6, 1)
SUMMER_END = (9, 15)
# ~11 productive hours per day, 5.5 h lost to the midday ban -> ~0.5
SUMMER_OUTDOOR_CAPACITY = 0.5


def in_summer_window(d: date) -> bool:
    return SUMMER_START <= (d.month, d.day) <= SUMMER_END


def capacity(d: date, calendar: str) -> float:
    if d.weekday() == FRIDAY:
        return 0.0
    if calendar == "outdoor" and in_summer_window(d):
        return SUMMER_OUTDOOR_CAPACITY
    return 1.0


def advance(start: date, units: float, calendar: str) -> date:
    """Return the finish date when `units` of work start on `start`."""
    if units <= 1e-9:
        return start - timedelta(days=1)  # zero-duration: finishes "before" start
    d, left = start, units
    while True:
        left -= capacity(d, calendar)
        if left <= 1e-9:
            return d
        d += timedelta(days=1)


def retreat(finish: date, units: float, calendar: str) -> date:
    """Latest start such that `units` of work finish on `finish`."""
    if units <= 1e-9:
        return finish + timedelta(days=1)
    d, left = finish, units
    while True:
        left -= capacity(d, calendar)
        if left <= 1e-9:
            return d
        d -= timedelta(days=1)


def _topo(tasks: dict[str, dict]) -> list[str]:
    order, seen, temp = [], set(), set()

    def visit(t):
        if t in seen:
            return
        if t in temp:
            raise ValueError(f"Dependency cycle at {t}")
        temp.add(t)
        for p in tasks[t]["predecessors"]:
            visit(p)
        temp.discard(t)
        seen.add(t)
        order.append(t)

    for t in tasks:
        visit(t)
    return order


def run(tasks: dict[str, dict], start: date, progress: dict[str, float] | None = None,
        as_of: date | None = None, extra_delay: dict[str, float] | None = None) -> dict:
    """Forward + backward pass.

    tasks: {task_id: {"duration_days": float, "predecessors": [ids], "calendar": str, ...}}
    progress: {task_id: 0..1}; None => baseline (nothing done).
    as_of: forecast date; remaining work cannot start before it.
    extra_delay: {task_id: extra working days} for what-if scenarios.
    """
    progress = progress or {}
    extra_delay = extra_delay or {}
    order = _topo(tasks)
    succ: dict[str, list[str]] = {t: [] for t in tasks}
    for t, v in tasks.items():
        for p in v["predecessors"]:
            succ[p].append(t)

    es, ef, units = {}, {}, {}
    for t in order:
        v = tasks[t]
        done = progress.get(t, 0.0) >= 0.999
        units[t] = 0.0 if done else float(v["duration_days"]) * (1 - progress.get(t, 0.0)) + extra_delay.get(t, 0.0)
        pred_finish = max((ef[p] for p in v["predecessors"]), default=None)
        s = start if pred_finish is None else pred_finish + timedelta(days=1)
        if as_of is not None and not done:
            s = max(s, as_of)
        es[t] = s
        ef[t] = advance(s, units[t], v["calendar"])
        if done and as_of is not None:
            ef[t] = min(ef[t], as_of - timedelta(days=1))

    project_finish = max(ef.values())
    ls, lf = {}, {}
    for t in reversed(order):
        lf[t] = min((ls[s] - timedelta(days=1) for s in succ[t]), default=project_finish)
        ls[t] = retreat(lf[t], units[t], tasks[t]["calendar"])

    out = {}
    for t in order:
        done = progress.get(t, 0.0) >= 0.999
        tf = None if done else (ls[t] - es[t]).days
        out[t] = {
            "task_id": t,
            "name": tasks[t].get("name", t),
            "calendar": tasks[t]["calendar"],
            "progress": round(progress.get(t, 0.0), 3),
            "remaining_units": round(units[t], 2),
            "start": es[t].isoformat(),
            "finish": ef[t].isoformat(),
            "total_float_days": tf,
            "critical": (tf is not None and tf <= 0),
            "complete": done,
        }
    return {"tasks": out, "finish": project_finish.isoformat()}


def forecast(tasks, start: date, as_of: date, progress: dict[str, float],
             extra_delay: dict[str, float] | None = None) -> dict:
    base = run(tasks, start)
    fc = run(tasks, start, progress=progress, as_of=as_of, extra_delay=extra_delay)
    b_end, f_end = date.fromisoformat(base["finish"]), date.fromisoformat(fc["finish"])
    for t, row in fc["tasks"].items():
        row["baseline_finish"] = base["tasks"][t]["finish"]
        if row["complete"]:  # no actual dates in sample data: show baseline dates for done tasks
            row["start"], row["finish"] = base["tasks"][t]["start"], base["tasks"][t]["finish"]
        row["finish_variance_days"] = (date.fromisoformat(row["finish"]) -
                                       date.fromisoformat(row["baseline_finish"])).days
    return {
        "as_of": as_of.isoformat(),
        "baseline_handover": base["finish"],
        "forecast_handover": fc["finish"],
        "handover_delay_days": (f_end - b_end).days,
        "critical_path": [t for t, r in fc["tasks"].items() if r["critical"]],
        "tasks": list(fc["tasks"].values()),
        "calendar_note": "Outdoor tasks use reduced capacity 1 Jun-15 Sep (midday restriction 10:00-15:30). Verify current rule.",
    }
