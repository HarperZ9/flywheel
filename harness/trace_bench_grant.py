"""Consent for a bulk bench replay (7.8 stage B2, I16, I17, SP-32).

`POST /api/traces/bench` needs an `endpoints` list; there is no default
ladder. Without one the answer is ENDPOINTS_REQUIRED with the statement that
each task's goal text goes to each named endpoint. With one, the gateway
refreshes the tasks from the traces and answers with a grant: every
reproducible task, the endpoints, and each task's capabilities as its
original run had them (a replay never gets more). A goal that holds a
credential refuses the whole grant before any transport call. The grant's
digest is what presence confirms, and the presence summary lists each goal
and endpoint, so the owner reads untrusted goals before approving. The
replay itself then needs that presence, and a grant whose tasks changed
since it was planned is refused (GRANT_DRIFTED).

The replay runs in the gateway process through `run_router_agent` with each
endpoint's own proposer; it is not queued as a separate gateway operation.
"""
from __future__ import annotations

import re

from .evidence_json import canonical_sha256

STATEMENT = ("Each task's goal text is sent to each named endpoint. Name the endpoints; "
             "there is no default.")
_ENDPOINT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:\-]{0,63}\Z")


class GrantError(Exception):
    def __init__(self, code: str, status: int) -> None:
        super().__init__(code)
        self.code, self.status = code, status


def _endpoints(value) -> list[str]:
    if type(value) is not list or not value:
        raise GrantError("ENDPOINTS_REQUIRED", 422)
    if len(value) > 8 or not all(type(e) is str and _ENDPOINT.fullmatch(e) for e in value):
        raise GrantError("INVALID_REQUEST", 422)
    return sorted(set(value))


def _caps(task: dict) -> dict:
    caps = task.get("capabilities") or {}
    return {"allow_write": caps.get("allow_write") is True,
            "allow_exec": caps.get("allow_exec") is True}


def plan_grant(home, owner: str, endpoints) -> dict:
    """The grant for replaying every reproducible task on `endpoints`."""
    from .trace_bench_tasks import BenchTasks, build_tasks
    from .trace_redact import scan
    from .trace_redact_rules import credential_rules
    endpoints = _endpoints(endpoints)
    build_tasks(home, owner)
    store = BenchTasks(home, owner)
    tasks = [store.read(r["task_ref"]) for r in store.index() if r["class"] == "REPRODUCIBLE"]
    held = [t["task_ref"] for t in tasks if scan(t["goal"], rules_=credential_rules())]
    if held:
        raise GrantError("CREDENTIAL_IN_GOAL", 422)
    rows = [{"task_ref": t["task_ref"], "goal_sha256": canonical_sha256({"goal": t["goal"]}),
             "capabilities": _caps(t)} for t in tasks]
    grant = {"schema": "flywheel.bench-replay-grant/v1", "endpoints": endpoints, "tasks": rows}
    lines = [f"Replay {len(tasks)} tasks on {', '.join(endpoints)}. {STATEMENT}"]
    lines += [f"- [{t['content_trust']}] {t['goal']} -> {', '.join(endpoints)}" for t in tasks]
    from .trace_presence_summary import remember
    remember("bench_replay", canonical_sha256(grant), "\n".join(lines))
    return {"grant_digest": canonical_sha256(grant), "grant": grant,
            "summary": [{"task_ref": t["task_ref"], "goal": t["goal"],
                         "content_trust": t["content_trust"], "endpoints": endpoints}
                        for t in tasks],
            "summary_text": "\n".join(lines)}


def _replay(home, owner: str, body: dict, proposer_for) -> tuple[dict, int]:
    from .trace_bench_replay import replay_tasks
    from .trace_presence import PresenceError, require
    from pathlib import Path
    grant = plan_grant(home, owner, body.get("endpoints"))
    if grant["grant_digest"] != body.get("grant_digest"):
        raise GrantError("GRANT_DRIFTED", 409)
    try:
        require(Path(home) / "state", owner, "bench_replay", grant["grant_digest"],
                body.get("presence_ref"))
    except PresenceError as exc:
        raise GrantError(exc.code, 403) from None
    report = replay_tasks(home, owner, grant["grant"]["endpoints"], proposer_for=proposer_for,
                          only={row["task_ref"] for row in grant["grant"]["tasks"]})
    return report, 200


def handle(home, owner: str, body: dict, *, proposer_for=None) -> tuple[dict, int]:
    """Plan a grant (no presence) or run a confirmed one."""
    try:
        if "grant_digest" in body or "presence_ref" in body:
            return _replay(home, owner, body, proposer_for)
        grant = plan_grant(home, owner, body.get("endpoints"))
        return {"schema": "flywheel.bench-replay-plan/v1", "statement": STATEMENT,
                "presence_kind": "bench_replay", **grant}, 202
    except GrantError as exc:
        return {"schema": "flywheel.error/v1", "code": exc.code, "statement": STATEMENT}, \
            exc.status
