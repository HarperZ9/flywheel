"""verification_meter.py -- cost to verify, per task family and route, and the full report.

For each task family: items and size per route, the unchecked share by count
with a Wilson interval, reviewer minutes summed over person-checked items, how
many person-checked items had minutes logged, and minutes per person-checked
item. A family whose unchecked share is above 0.5 is marked hold_on_completion.
"""
from __future__ import annotations

from collections import defaultdict

from .verification_share import (DOES_NOT_PROVE, HOLD_ON_COMPLETION_ABOVE, ROUTES, flag_weeks,
                                 weekly, wilson)


def _family_row(items: list) -> dict:
    counts = {r: sum(1 for it in items if it.route == r) for r in ROUTES}
    sizes = {r: sum(it.size for it in items if it.route == r) for r in ROUTES}
    person = [it for it in items if it.route == "person"]
    logged = [it.reviewer_minutes for it in person if it.reviewer_minutes is not None]
    unchecked = wilson(counts["unchecked"], len(items))
    return {
        "items": len(items), "count": counts, "size": sizes,
        "unchecked_share": unchecked,
        "reviewer_minutes": sum(logged),
        "minutes_logged": [len(logged), len(person)],
        "minutes_per_person_item": round(sum(logged) / len(logged), 1) if logged else None,
        "hold_on_completion": bool(unchecked[0] is not None and unchecked[0] > HOLD_ON_COMPLETION_ABOVE),
    }


def meter(items: list) -> dict:
    by_family: dict = defaultdict(list)
    for it in items:
        by_family[it.family].append(it)
    return {fam: _family_row(rows) for fam, rows in sorted(by_family.items())}


def report(items: list) -> dict:
    weeks = weekly(items)
    person = [it for it in items if it.route == "person"]
    logged = sum(1 for it in person if it.reviewer_minutes is not None)
    return {
        "schema": "flywheel.verification-share-report/v1",
        "items": len(items),
        "weeks": weeks,
        "flags": flag_weeks(weeks),
        "cost_to_verify": meter(items),
        "minutes_coverage": [logged, len(person)],
        "does_not_prove": DOES_NOT_PROVE,
    }


def render(rep: dict) -> str:
    lines = ["week      items   size  machine  person  unchecked"]
    for w in rep["weeks"]:
        s = w["share"]
        fmt = lambda v: "   -  " if v is None else f"{v:6.2f}"  # noqa: E731
        lines.append(f"{w['week']}  {w['items']:5} {w['size']:6}  {fmt(s['machine'])}  "
                     f"{fmt(s['person'])}  {fmt(s['unchecked'])}")
    for f in rep["flags"]:
        lines.append(f"FLAG {f['week']}: unchecked share rose {f['unchecked_share']} "
                     f"while output grew {f['size']}")
    width = max([len(f) for f in rep["cost_to_verify"]] + [6]) + 2
    lines.append(f"{'family':{width}} items  unchecked [95%]          minutes  logged")
    for fam, row in rep["cost_to_verify"].items():
        u = row["unchecked_share"]
        mark = "  hold-on-completion" if row["hold_on_completion"] else ""
        lines.append(f"{fam:{width}} {row['items']:5}  {u[0]:.2f} [{u[1]:.2f}, {u[2]:.2f}]"
                     f"  {row['reviewer_minutes']:7}  {row['minutes_logged'][0]}/"
                     f"{row['minutes_logged'][1]}{mark}")
    lines.append(rep["does_not_prove"])
    return "\n".join(lines)
