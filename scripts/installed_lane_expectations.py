"""The expected row for each lane in the installed-app lane acceptance.

``packaging/installed-lane-expectations.json`` names, per lane, the verdict the
run must reach (``AT_CLASS``, ``BELOW_BAR`` or ``HELD``) and, for the last two,
the exact failed checks it may carry. ``judge`` compares a run with the rows:

- a lane whose verdict differs from its row departs, in either direction, so
  a lane that starts reaching its class changes the claim and the row together;
- a ``BELOW_BAR`` lane departs when its failed checks are not exactly the
  listed ones;
- a ``HELD`` lane departs on any failed check, so a held lane that launched
  turns the step red;
- a lane with no row, or a row with no lane, departs.

The frozen smoke (``packaging/lane-smoke-expectations.json``) has worked this
way since 1.0.4; the installed step now does too.
"""
from __future__ import annotations

import json
from pathlib import Path

EXPECTATIONS = Path(__file__).resolve().parents[1] / "packaging" / "installed-lane-expectations.json"
VERDICTS = frozenset(("AT_CLASS", "BELOW_BAR", "HELD"))


def load(path: Path = EXPECTATIONS) -> dict[str, dict]:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))["lanes"]
    for lane, row in rows.items():
        if row.get("verdict") not in VERDICTS:
            raise ValueError(f"{lane}: unknown expected verdict {row.get('verdict')!r}")
    return rows


def _failed(row: dict) -> list[str]:
    return sorted(item.get("check", "") for item in row.get("failed", []))


def judge(lanes: dict[str, dict], rows: dict[str, dict] | None = None) -> dict:
    """{"matches": bool, "departures": [{"lane", "expected", "observed"}...]}."""
    rows = load() if rows is None else rows
    departures = []
    for lane in sorted(set(rows) | set(lanes)):
        want, got = rows.get(lane), lanes.get(lane)
        if want is None or got is None:
            departures.append({"lane": lane, "expected": want, "observed":
                               None if got is None else got.get("verdict")})
            continue
        observed = {"verdict": got.get("verdict"), "failed": _failed(got)}
        wanted = {"verdict": want["verdict"], "failed": sorted(want.get("failed", []))}
        if observed != wanted:
            departures.append({"lane": lane, "expected": wanted, "observed": observed})
    return {"matches": not departures, "departures": departures}
