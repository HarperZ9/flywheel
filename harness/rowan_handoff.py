"""rowan_handoff.py -- a Rowan run as a brief another agent can pick up.

A user who moves a task to another agent should not have to re-explain it.
This exporter reads one run's private trace and writes a provider-neutral
Markdown brief: the goal, where the run ended, what was done, the model's own
stated steps, what is still open, the final answer, and the receipts that bind
the brief to the recorded run.

It is a plain exporter. It re-runs nothing and re-verifies nothing: the
verified, claimed and failed marks are the ones recorded when the run ended,
and the model's words are labelled as its words. Rendering context for a
particular provider belongs elsewhere.
"""
from __future__ import annotations

import json

SCHEMA = "flywheel.rowan-handoff/v1"
MAX_LINES = 20
DOES_NOT_PROVE = ["NOT_RE_VERIFIED_AT_EXPORT", "NOT_SEMANTIC_TRUTH",
                  "FILE_CONTENTS_NOT_INCLUDED"]


def _one_line(text, limit: int = 200) -> str:
    flat = " ".join(str(text or "").split())
    return flat if len(flat) <= limit else flat[:limit - 3] + "..."


def _quote(text) -> str:
    lines = str(text or "").strip().splitlines() or ["(empty)"]
    return "\n".join("> " + line for line in lines[:60])


def _terminal(records: list) -> dict:
    for record in reversed(records):
        if record.get("kind") in {"result", "failure"}:
            return record
    return {"kind": "none", "payload": {}}


def _goal(records: list) -> str:
    for record in records:
        if record.get("kind") == "request":
            return str(record["payload"].get("operation", {}).get("goal", ""))
    return ""


def _ledger(records: list) -> list[dict]:
    return [r["payload"] for r in records if r.get("kind") == "ledger"]


def _commands(records: list) -> list[str]:
    lines = []
    for entry in _ledger(records):
        name, _, rest = str(entry.get("content", "")).partition(" ")
        if entry.get("kind") == "tool_call" and name == "run":
            try:
                lines.append(str(json.loads(rest).get("cmd", "")))
            except ValueError:
                lines.append(rest)
    for record in records:
        payload = record.get("payload") or {}
        if record.get("kind") == "progress" and payload.get("type") == "cli_tool_call" \
                and payload.get("tool") == "Bash":
            lines.append(str((payload.get("arguments") or {}).get("command", "")))
    return lines


def _stated_steps(records: list) -> list[str]:
    steps = [_one_line(e.get("content")) for e in _ledger(records)
             if e.get("kind") == "assistant" and str(e.get("content", "")).strip()]
    steps += [_one_line(r["payload"].get("text")) for r in records
              if r.get("kind") == "progress" and r["payload"].get("type") == "cli_message"]
    return steps


def _ended(state: str, reason, terminal: dict) -> list[str]:
    payload = terminal["payload"]
    lines = [f"- Run state: {state}" + (f" ({reason})" if reason else "")]
    completion = payload.get("completion") or {}
    counts = completion.get("counts")
    if isinstance(counts, dict):
        lines.append(f"- Completion: {completion.get('verdict')}. Verified "
                     f"{counts.get('verified', 0)}, claimed {counts.get('claimed', 0)}, "
                     f"failed {counts.get('failed', 0)}.")
    else:
        lines.append("- Completion: no record. Treat every outcome as unconfirmed.")
    budget = payload.get("run_budget") or {}
    if budget.get("tripped"):
        lines.append(f"- Budget: stopped on {budget['tripped']}.")
    elif budget:
        used = budget.get("used", {})
        lines.append(f"- Budget: within limits; {used.get('model_calls', 0)} model calls, "
                     f"{used.get('tool_actions', 0)} tool actions.")
    return lines


def _deliverables(terminal: dict) -> list[str]:
    items = (terminal["payload"].get("completion") or {}).get("items") or []
    lines = []
    for item in items:
        check = item.get("check") or "no check"
        label = item.get("path") if item.get("kind") == "file" else "Final answer"
        lines.append(f"- {label}: {item.get('status')} ({check}, {item.get('detail')})")
    return lines


def _open_items(state: str, reason, terminal: dict) -> list[str]:
    payload = terminal["payload"]
    completion = payload.get("completion") or {}
    lines = []
    if state != "completed":
        lines.append(f"- The run did not finish ({reason or state}). Pick up from the "
                     "last stated step.")
    for item in completion.get("items") or []:
        name = item.get("path") or "the final answer"
        if item.get("status") == "claimed":
            lines.append(f"- Check {name}: it is claimed and nothing verified it.")
        elif item.get("status") == "failed":
            lines.append(f"- Fix {name}: its check failed ({item.get('detail')}).")
    if completion.get("unbacked_success_claim"):
        lines.append("- The answer says it succeeded, but no check backs that claim.")
    budget = payload.get("run_budget") or {}
    if budget.get("false_success_count"):
        lines.append(f"- {budget['false_success_count']} step(s) exited 0 while reporting "
                     "a rate limit, quota, billing or sign-in error.")
    return lines or ["- None recorded."]


def _receipts(records: list, projection: dict, terminal: dict) -> list[str]:
    payload = terminal["payload"]
    lines = [f"- Operation: `{projection.get('operation_ref')}`",
             f"- Journey: `{projection.get('journey_ref')}`",
             f"- Private trace: `{projection.get('trace_ref')}`, {len(records)} records, "
             f"head `{records[-1]['record_sha256'] if records else 'none'}`"]
    if payload.get("checkpoint"):
        lines.append(f"- Ledger checkpoint: `{payload['checkpoint']}` "
                     f"(chain verified at run end: {payload.get('verified')})")
    verdict = payload.get("verdict")
    if isinstance(verdict, dict):
        lines.append(f"- Run verdict: accepted={verdict.get('accepted')}, "
                     f"chain_intact={verdict.get('chain_intact')}")
    return lines


def _capped(lines: list[str]) -> list[str]:
    if len(lines) <= MAX_LINES:
        return lines
    return lines[:MAX_LINES] + [f"- and {len(lines) - MAX_LINES} more in the trace"]


def _section(title: str, lines: list[str], empty: str) -> str:
    return f"## {title}\n\n" + "\n".join(lines or [empty])


def handoff_markdown(records: list, projection: dict) -> str:
    """Render one run's trace as a Markdown brief for another agent."""
    terminal = _terminal(records)
    state, reason = projection.get("state", "unknown"), projection.get("reason")
    goal = _goal(records)
    final = terminal["payload"].get("final")
    commands = [f"- `{_one_line(c, 160).replace('`', chr(39))}`" for c in _commands(records)]
    steps = [f"{i}. {s}" for i, s in enumerate(_stated_steps(records), 1)]
    return "\n\n".join([
        f"# Handoff: {_one_line(goal, 80) or 'Rowan run'}",
        "Exported from a recorded Rowan run so another agent can continue it. "
        "Nothing was re-run or re-checked for this export. The marks below are "
        "the ones recorded when the run ended, and the model's words are "
        "labelled as its words.",
        _section("Goal", [_quote(goal)], ""),
        _section("Where it ended", _ended(state, reason, terminal), ""),
        _section("Deliverables", _capped(_deliverables(terminal)), "- None recorded."),
        _section("Commands run", _capped(commands), "- None."),
        _section("Steps the model stated (its words, not checked)", _capped(steps),
                 "- None recorded."),
        _section("Open items", _open_items(state, reason, terminal), ""),
        _section("Final answer (the model's words)", [_quote(final)] if final else [],
                 "No final answer was recorded."),
        _section("Receipts", _receipts(records, projection, terminal), ""),
        "File contents are not included. Ask the owner for the workspace, or "
        "reproduce the deliverables and rerun their checks.",
    ]) + "\n"


def read_handoff(service, owner_ref: str, operation_ref: str) -> dict:
    """The owner's brief for one run, bound to the trace it was read from."""
    from .gateway_agent_trace import AgentTrace, TraceError
    from .gateway_operation import GatewayOperationError
    snapshot = service.snapshot(owner_ref, operation_ref)
    if snapshot.state not in {"completed", "failed", "cancelled"}:
        raise GatewayOperationError("INVALID_TRANSITION")
    projection = service.result(owner_ref, operation_ref)["result"]
    try:
        trace = AgentTrace(service.state_root, owner_ref, snapshot.journey_ref, operation_ref)
        records = trace.read()
    except TraceError:
        raise GatewayOperationError("STORE_COMMIT_FAILED") from None
    if (projection.get("trace_ref") != trace.ref
            or projection.get("record_count") != len(records)
            or projection.get("trace_head_sha256") != trace.head):
        raise GatewayOperationError("NOT_FOUND")
    return {"schema": SCHEMA, "operation_ref": operation_ref,
            "journey_ref": snapshot.journey_ref, "trace_ref": trace.ref,
            "record_count": len(records), "trace_head_sha256": trace.head,
            "markdown": handoff_markdown(records, projection),
            "does_not_prove": list(DOES_NOT_PROVE)}
