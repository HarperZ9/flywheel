"""optional_rules.py -- owner overlays that ship with Flywheel but are off by default.

An optional overlay is a set of extra HOLD rules an owner can switch on. It goes
through the same additive overlay path as any owner rule (rules.load_pack), so
it can only add stops, and switching it on changes the monitor config digest,
never the shipped pack digest.

side-effect-tools (scope-escape/004) holds tool calls whose names say they post,
send, delete, update, trash, reset, pay, transfer or start a server. It is off
by default: its measured recall on side-effecting tool names was below the bar,
and the holds per hour it would add to a working agent are unmeasured. The
measurement lives in tests/test_preaction_tool_names.py.
"""
from __future__ import annotations

import copy

SIDE_EFFECT_TOOLS_RULE = {
    "id": "scope-escape/004",
    "family": "scope-escape",
    "action": "HOLD",
    "reason": "Calls a tool whose name says it posts, sends, deletes, updates, pays, "
              "resets or starts a server.",
    "match": {
        "kinds": ["mcp", "unknown"],
        "tool_regex": "(?i)(^|__)(post|send|delete|update|trash)_|create_draft|reset|"
                      "recovery|payment|transfer|start_[a-z0-9_]*server",
    },
}

OPTIONAL_OVERLAYS = {
    "side-effect-tools": {"rules": [SIDE_EFFECT_TOOLS_RULE]},
}


def optional_overlay(name: str) -> dict:
    """A copy of the named optional overlay, ready for MonitorConfig.rules_overlay."""
    if name not in OPTIONAL_OVERLAYS:
        raise KeyError(f"unknown optional overlay {name!r}; known: {sorted(OPTIONAL_OVERLAYS)}")
    return copy.deepcopy(OPTIONAL_OVERLAYS[name])


def with_optional(overlay: dict | None, *names: str) -> dict:
    """The owner's overlay with the named optional overlays' rules appended.

    Host lists in the owner's overlay are kept. A rule id that already appears
    is not added twice.
    """
    merged = copy.deepcopy(overlay or {})
    rules = merged.setdefault("rules", [])
    seen = {r.get("id") for r in rules}
    for name in names:
        for rule in optional_overlay(name)["rules"]:
            if rule["id"] not in seen:
                rules.append(rule)
                seen.add(rule["id"])
    return merged
