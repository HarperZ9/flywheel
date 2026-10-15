"""config_hash.py -- one hash for the harness settings a turn ran under.

Two runs with the same model can differ because the harness around the model
differed: another system prompt, another tool set, another mode or budget.
The hash covers every setting that shapes what the model is sent or what the
loop lets it do, so equal hashes mean same-harness runs and a delta between
two runs with equal hashes cannot be put down to the harness.

Covered: the full system prompt as sent (tool texts, instruction files, skills
and memory notes are in it), permission mode, permission rules, hook entries,
max steps, compaction budget, max tokens, temperature, seed, the backend
preference, which backends and models answered, the test command and the
Flywheel version. Not covered: the user's own words, the clock, and an
"always" answer given at a prompt mid-session (the approval itself is on the
ledger).
"""
from __future__ import annotations

import hashlib
import json

SCHEMA = "flywheel.harness-config/v1"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _version() -> str:
    try:
        from harness.cli_version import installed_version
        return installed_version()
    except Exception:  # a missing version must not stop a turn; it hashes as unknown
        return "unknown"


def _answered(session, ledger_from: int) -> list:
    """(backend, model) for each backend that answered since ledger_from, in order."""
    by_name = {getattr(b, "name", ""): b for b in getattr(session.agent, "backends", [])}
    seen = []
    for e in session.ledger.entries[ledger_from:]:
        if e.kind != "assistant":
            continue
        name = (e.meta or {}).get("backend") or ""
        b = by_name.get(name)
        model = (getattr(b, "model", "") or getattr(b, "_resolved", "")) if b else ""
        if [name, model] not in seen:
            seen.append([name, model])
    return seen


def harness_config(session, ledger_from: int = 0) -> dict:
    agent, ex = session.agent, session.executor
    rules = getattr(ex, "rules", None)
    hooks = getattr(session, "hooks", None)
    return {
        "schema": SCHEMA,
        "system_sha256": _sha(getattr(agent, "system", "") or ""),
        "mode": ex.mode,
        "rules": ({"allow": list(rules.allow), "deny": list(rules.deny)} if rules else None),
        "hooks": sorted([e.event, e.matcher, e.command] for e in getattr(hooks, "entries", [])),
        "max_steps": session.max_steps,
        "compact_budget": session.compact_budget,
        "max_tokens": getattr(agent, "max_tokens", None),
        "temperature": getattr(agent, "temperature", None),
        "seed": getattr(agent, "seed", None),
        "prefer": getattr(agent, "prefer", None),
        "answered": _answered(session, ledger_from),
        "test_cmd": session.test_cmd,
        "flywheel": _version(),
    }


def config_sha256(config: dict) -> str:
    return _sha(json.dumps(config, sort_keys=True, ensure_ascii=False))


def record(session, ledger_from: int) -> str:
    """Hash this turn's config; add a ledger entry when it differs from the last one."""
    config = harness_config(session, ledger_from)
    digest = config_sha256(config)
    if getattr(session, "config_sha256", "") != digest:
        session.ledger.append("harness_config", json.dumps(config, sort_keys=True),
                              {"sha256": digest})
    session.config_sha256 = digest
    return digest
