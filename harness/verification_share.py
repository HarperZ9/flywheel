"""verification_share.py -- is verification keeping up with what ships?

Each shipped item (a merged change, a released result) carries a route: machine
(re-derived against an independent check), person (a person checked it), or
unchecked. Per ISO week this module reports how much output shipped and what
share of it went each route, weighted by size. It raises a flag in the week
when the unchecked share has risen two weeks running while output grew over
the same two weeks: generation outpacing verification.

The cost-to-verify meter groups items by task family and route, sums the
reviewer minutes logged for person-checked items, and says how many of those
items had minutes logged at all. A family whose unchecked share is above 0.5
is marked for hold-on-completion until a check exists for it.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime

SCHEMA = "flywheel.shipped-item/v1"
ROUTES = ("machine", "person", "unchecked")
LANE_TO_ROUTE = {"A": "machine", "H": "person", "UNVERIFIABLE": "unchecked"}
HOLD_ON_COMPLETION_ABOVE = 0.5
DOES_NOT_PROVE = (
    "A route says which kind of check an item went through, not that the check was "
    "right. Shares are weighted by the size each source reports; reviewer minutes "
    "are self-logged.")


@dataclass(frozen=True)
class Item:
    item_id: str
    shipped_at: str
    family: str
    route: str
    size: int
    reviewer_minutes: int | None = None

    def __post_init__(self) -> None:
        if self.route not in ROUTES:
            raise ValueError(f"route must be one of {ROUTES}")
        if type(self.size) is not int or self.size < 0:
            raise ValueError("size must be a non-negative int")
        m = self.reviewer_minutes
        if m is not None and (type(m) is not int or m < 0):
            raise ValueError("reviewer_minutes must be a non-negative int or null")
        _parse_day(self.shipped_at)

    def week(self) -> str:
        y, w, _ = _parse_day(self.shipped_at).isocalendar()
        return f"{y}-W{w:02d}"


def _parse_day(stamp: str) -> date:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).date()


def item_from_dict(d: dict) -> Item:
    if d.get("schema", SCHEMA) != SCHEMA:
        raise ValueError(f"unknown shipped-item schema {d.get('schema')!r}")
    route = d.get("route") or LANE_TO_ROUTE.get(d.get("lane", ""), "")
    return Item(str(d["id"]), d["shipped_at"], str(d.get("family") or "unspecified"),
                route, d.get("size", 0), d.get("reviewer_minutes"))


def wilson(k: int, n: int, z: float = 1.959964) -> list:
    if n == 0:
        return [None, None, None]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(p, 4), round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def weekly(items: list) -> list:
    """One row per ISO week, in order, with output size, item counts and
    size-weighted route shares. Weeks with nothing shipped are not invented."""
    by_week: dict = defaultdict(lambda: {"items": 0, "size": 0, **{r: 0 for r in ROUTES}})
    for it in items:
        row = by_week[it.week()]
        row["items"] += 1
        row["size"] += it.size
        row[it.route] += it.size
    out = []
    for week in sorted(by_week):
        row = by_week[week]
        size = row["size"]
        shares = {r: (round(row[r] / size, 4) if size else None) for r in ROUTES}
        out.append({"week": week, "items": row["items"], "size": size, "share": shares})
    return out


def flag_weeks(weeks: list) -> list:
    """Weeks where the unchecked share rose two weeks running while output grew."""
    flagged = []
    for a, b, c in zip(weeks, weeks[1:], weeks[2:]):
        ua, ub, uc = (w["share"]["unchecked"] for w in (a, b, c))
        if None in (ua, ub, uc):
            continue
        if ua < ub < uc and a["size"] < b["size"] < c["size"]:
            flagged.append({"week": c["week"], "unchecked_share": [ua, ub, uc],
                            "size": [a["size"], b["size"], c["size"]]})
    return flagged
