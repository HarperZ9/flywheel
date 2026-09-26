"""One lane's state, from the engine only.

The lane card reads ``state`` and a sentence, never the health verdict alone.
A health answer never produces "Runs" (H-2): a lane is ``ready`` only when a
main tool from the policy table is listed by the lane's own server and every
setup item that tool needs is met.

States (PLAN section 2):

- ``not_checked``   no probe under this engine version and lane pin;
- ``ready``         a main tool runs; nothing else waits;
- ``limited``       a main tool runs; other listed tools wait on named items;
- ``needs_setup``   no main tool can run until a named step is done;
- ``reads_only``    a class C lane; the action runs somewhere else;
- ``cannot_launch`` the launch failed for a defect, with a code;
- ``unreachable``   an http lane the probe could not reach.

A row probed by an earlier engine session keeps its answer and reads "Last
checked <time>" until a probe in this session replaces it (H-10).
"""
from __future__ import annotations

from typing import Iterable, Mapping

from .lane_probe_cache import ProbeCache, default_cache, lane_pin, slug
from .lane_setup import SetupChecks, SetupItem
from .lane_tool_policy import READS_ONLY_LANES, lane_policy, main_tools

STATES = ("not_checked", "ready", "limited", "needs_setup", "reads_only",
          "cannot_launch", "unreachable")
MAIN_ACTIONS = {
    "gather": "catalog a local document and pull feeds",
    "crucible": "check a thesis against measurements",
    "chorus": "digest a corpus into themes",
    "articulate": "score and check prose",
    "index": "map a repo and find symbols",
    "forum": "run a deliberation room",
    "learn": "plan and check a study step",
    "telos": "read the workstation catalog and proofs",
    "local-model": "run a local agent task in a project",
    "writing": "diagnose a draft",
    "relay": "run one agent task through a local model",
    "plexus": "plan a route between lanes",
    "mneme": "remember and recall a fact",
    "calibrate-pro": "look up a panel profile",
    "canon": "validate context blocks",
    "bulletin": "read board rooms and feed",
    "accountable-surface": "perceive a folder with provenance",
}
HEALTH_LINE = "Answers its health check."


def _runtime_block(row: Mapping[str, object]) -> tuple[str, list[str], str] | None:
    """(state, setup item ids, code) when the runtime selection blocks the lane."""
    from .lane_runtime_frozen import SETUP_CODES, launch_state, setup_items
    codes = [str(c) for c in row.get("blocking_codes") or ()]
    if codes:
        if launch_state(codes) == "needs_setup":
            return "needs_setup", list(setup_items(codes)), ""
        defects = [c for c in codes if c not in SETUP_CODES]
        return "cannot_launch", [], slug(defects[0] if defects else codes[0], "runtime_blocked")
    if row.get("status") == "missing":
        return "cannot_launch", [], "not_installed"
    return None


def _from_probe(lane: str, record: Mapping[str, object],
                checks: SetupChecks) -> tuple[str, list[str], str, dict]:
    """(state, unmet items, code, extra) for a lane whose health answered."""
    policy = lane_policy(lane)
    listed = set(record.get("tools") or ())
    mains = [t for t in main_tools(lane) if t in listed]
    if not mains:
        return "cannot_launch", [], "main_tool_not_admitted", {}

    def unmet(tool: str) -> list[str]:
        return [i for i in policy[tool].needs if not checks.item(i, lane).met]

    ready = [t for t in mains if not unmet(t)]
    if not ready:
        items = list(dict.fromkeys(i for t in mains for i in unmet(t)))
        return "needs_setup", items, "", {"health_answered": True}
    waiting = {t: unmet(t) for t in sorted(listed) if t in policy and t not in ready}
    waiting = {t: items for t, items in waiting.items() if items}
    if not waiting:
        return "ready", [], "", {"ready_tools": ready}
    items = list(dict.fromkeys(i for found in waiting.values() for i in found))
    return "limited", items, "", {"ready_tools": ready, "waiting_tools": sorted(waiting)}


def _decide(lane: str, row: Mapping[str, object], record: dict | None,
            checks: SetupChecks) -> tuple[str, list[str], str, dict]:
    blocked = _runtime_block(row)
    if blocked is not None:
        return (*blocked, {})
    outcome = record.get("outcome") if record else None
    if outcome == "cannot_launch":
        return "cannot_launch", [], slug(record.get("code"), "launch_failed"), {}
    if outcome == "unhealthy":
        return "cannot_launch", [], "health_check_failed", {}
    if lane in READS_ONLY_LANES:
        return "reads_only", [], "", {}
    if outcome == "unreachable":
        return "unreachable", [], "network_error", {}
    if outcome == "answered":
        return _from_probe(lane, record, checks)
    return "not_checked", [], "", {}


def _sentence(lane: str, state: str, items: list[SetupItem], code: str,
              extra: dict) -> tuple[str, str]:
    action = MAIN_ACTIONS.get(lane, "its main action")
    if state == "ready":
        return f"Runs {action}.", ""
    if state == "limited":
        names = ", ".join(i.title for i in items)
        return f"Runs {action}. {len(extra.get('waiting_tools', ()))} tools need: {names}.", ""
    if state == "needs_setup":
        first = items[0].copy if items else "A setup step is needed."
        return first, HEALTH_LINE if extra.get("health_answered") else ""
    if state == "reads_only":
        return READS_ONLY_LANES.get(lane, "Reads only."), ""
    if state == "cannot_launch":
        return f"Could not start: {code}.", ""
    if state == "unreachable":
        from .lanes_registry import LANES
        return f"Cannot reach {LANES[lane].endpoint()}.", ""
    return "Not checked yet.", ""


def lane_state(lane: str, row: Mapping[str, object], *, cache: ProbeCache | None = None,
               checks: SetupChecks | None = None) -> dict:
    """The state fields one roster row carries."""
    cache = cache or default_cache()
    checks = checks or SetupChecks()
    record, fresh = cache.lookup(lane, lane_pin(lane))
    state, item_ids, code, extra = _decide(lane, row, record, checks)
    items = [checks.item(i, lane) for i in item_ids]
    sentence, second = _sentence(lane, state, items, code, extra)
    checked_at = record.get("checked_at") if record else None
    checked = (f"Checked {checked_at}." if fresh else f"Last checked {checked_at}."
               ) if checked_at else ""
    return {"state": state, "sentence": sentence, "second_line": second,
            "checked_line": checked, "last_checked": checked_at,
            "checked_this_session": bool(record and fresh), "code": code,
            "setup": [i.to_dict() for i in items], "main_action": MAIN_ACTIONS.get(lane, ""),
            "main_tools": main_tools(lane), **{k: v for k, v in extra.items()
                                              if k in ("ready_tools", "waiting_tools")}}


def roster_rows(rows: Iterable[dict], *, probed: bool, cache: ProbeCache | None = None,
                checks: SetupChecks | None = None) -> list[dict]:
    """Record probed rows, then add each row's state fields."""
    from .lanes_registry import LANES
    cache = cache or default_cache()
    checks = checks or SetupChecks()
    out = []
    for row in rows:
        name = str(row.get("name", ""))
        if name not in LANES:
            out.append(dict(row))
            continue
        if probed:
            cache.record_row(name, lane_pin(name), row, http=LANES[name].kind == "http")
        out.append({**row, **lane_state(name, row, cache=cache, checks=checks)})
    return out


def by_state(rows: Iterable[Mapping[str, object]]) -> dict[str, int]:
    counts = {state: 0 for state in STATES}
    for row in rows:
        state = row.get("state")
        if state in counts:
            counts[state] += 1
    return counts
