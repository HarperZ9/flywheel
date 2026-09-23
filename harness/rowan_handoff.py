"""rowan_handoff.py -- a Rowan run as a brief another agent can pick up.

A user who moves a task to another agent should not have to re-explain it.
This exporter reads one run's private trace and writes a provider-neutral
Markdown brief: the goal, where the run ended, what was done, the model's own
stated steps, what is still open, the final answer, and the receipts that bind
the brief to the recorded run.

It re-runs nothing. The verified, claimed and failed marks are the ones
recorded when the run ended, shown only after the same gateway recheck the
Rowan card uses: a completion record the trace does not support is printed as
unverifiable, with every mark marked unconfirmed. The model's words are
labelled as its words. Everything that leaves goes through rowan_handoff_text
first, so credentials, host paths and file contents stay on the machine.
"""
from __future__ import annotations

import json

from .rowan_handoff_text import code, one_line, outbound, quote, safe_line

SCHEMA = "flywheel.rowan-handoff/v1"
MAX_LINES = 20
#: Character budgets for the two quoted fields. At four bytes a character the
#: whole brief stays well under the desktop's 1 MiB limit.
GOAL_CHARS, FINAL_CHARS = 8_000, 40_000
DOES_NOT_PROVE = ["NOT_RE_VERIFIED_AT_EXPORT", "NOT_SEMANTIC_TRUTH",
                  "FILE_CONTENTS_NOT_INCLUDED", "REDACTION_IS_PATTERN_BASED"]
_TERMINAL = {"completed", "failed", "cancelled"}


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
            except (ValueError, AttributeError):
                lines.append(rest)
    for record in records:
        payload = record.get("payload") or {}
        if record.get("kind") == "progress" and payload.get("type") == "cli_tool_call" \
                and payload.get("tool") == "Bash":
            lines.append(str((payload.get("arguments") or {}).get("command", "")))
    return lines


def _step(text, root) -> str | None:
    """A model reply as a step: its prose, then only the name and path of each
    tool it called. A TOOL line's arguments carry file content, and file
    content does not leave in a brief."""
    from .tool_rescue import rescue_tool_calls
    lines = str(text or "").splitlines()
    cut = next((i for i, ln in enumerate(lines) if ln.lstrip().startswith("TOOL ")), None)
    prose = one_line(outbound("\n".join(lines[:cut]), root), 160)
    if cut is None:
        return prose or None
    calls, _ = rescue_tool_calls("\n".join(lines[cut:]))
    named = [call[0] + (" " + code(call[1]["path"], root, 120)
                        if isinstance(call[1], dict) and call[1].get("path") else "")
             for call in calls[:6]]
    tools = f"[tools: {', '.join(named) or 'unparsed'}]"
    return f"{prose} {tools}" if prose else tools


def _stated_steps(records: list, root) -> list[str]:
    texts = [e.get("content") for e in _ledger(records) if e.get("kind") == "assistant"]
    texts += [r["payload"].get("text") for r in records
              if r.get("kind") == "progress" and r["payload"].get("type") == "cli_message"]
    return [s for s in (_step(t, root) for t in texts) if s]


def _outcome(records: list, state: str) -> dict:
    """The rechecked completion and budget blocks the card shows."""
    if state not in _TERMINAL:
        return {"completion": {"status": "unverifiable", "reason": "RUN_NOT_TERMINAL"},
                "budget": {"status": "unrecorded"}}
    from .gateway_run_outcome import derive_run_outcome
    return derive_run_outcome(records, terminal_state=state)


def _ended(state: str, reason, completion: dict, budget: dict) -> list[str]:
    lines = [f"- Run state: {state}" + (f" ({reason})" if reason else "")]
    if completion.get("status") == "recorded":
        counts = completion["counts"]
        lines.append(f"- Completion: {completion['verdict']}. Verified "
                     f"{counts['verified']}, claimed {counts['claimed']}, "
                     f"failed {counts['failed']}.")
    elif completion.get("status") == "unverifiable":
        lines.append(f"- Completion: unverifiable ({completion['reason']}). The record "
                     "does not match the trace. Treat every outcome as unconfirmed.")
    else:
        lines.append("- Completion: no record. Treat every outcome as unconfirmed.")
    if budget.get("status") == "stopped":
        lines.append(f"- Budget: stopped on {budget['tripped']}.")
    elif budget.get("status") == "within_limits":
        used = budget["used"]
        lines.append(f"- Budget: within limits; {used['model_calls']} model calls, "
                     f"{used['tool_actions']} tool actions.")
    elif budget.get("status") == "unverifiable":
        lines.append(f"- Budget: record unverifiable ({budget['reason']}).")
    return lines


def _items(report: dict) -> list[dict]:
    """The recorded items, final answer first so a cap never hides it."""
    items = [i for i in report.get("items") or [] if isinstance(i, dict)]
    return ([i for i in items if i.get("kind") == "final_answer"]
            + [i for i in items if i.get("kind") != "final_answer"])


def _label(item: dict, root) -> str:
    return (code(item.get("path"), root) if item.get("kind") == "file"
            else "Final answer")


def _deliverables(report: dict, confirmed: bool, root) -> list[str]:
    lines = []
    for item in _items(report):
        if confirmed:
            check = item.get("check") or "no check"
            mark = f"{item.get('status')} ({check}, {item.get('detail')})"
        else:
            mark = f"recorded as {item.get('status')}, not confirmed"
        lines.append(f"- {_label(item, root)}: {mark}")
    return _capped(lines, report.get("items_omitted", 0))


def _open_items(state: str, reason, report: dict, completion: dict, payload: dict,
                root) -> list[str]:
    lines = []
    if state != "completed":
        lines.append(f"- The run did not finish ({reason or state}). Pick up from the "
                     "last stated step.")
    confirmed = completion.get("status") == "recorded"
    if not confirmed:
        lines.append("- Recheck every deliverable: the completion record could not be "
                     f"confirmed ({completion.get('reason', 'no record')}).")
    for item in _items(report) if confirmed else []:
        name = code(item["path"], root) if item.get("kind") == "file" else "the final answer"
        if item.get("status") == "claimed":
            lines.append(f"- Check {name}: it is claimed and nothing verified it.")
        elif item.get("detail") == "not_run":
            lines.append(f"- Run the check on {name}: the step budget ran out before "
                         "the check command ran, so nothing was observed to fail.")
        elif item.get("status") == "failed":
            lines.append(f"- Fix {name}: its check failed ({item.get('detail')}).")
    if confirmed and completion.get("unbacked_success_claim"):
        lines.append("- The answer says it succeeded, but no check backs that claim.")
    budget = payload.get("run_budget") or {}
    if budget.get("false_success_count"):
        lines.append(f"- {budget['false_success_count']} step(s) exited 0 while the output "
                     "named a rate limit, quota, billing, sign-in or service-overloaded "
                     "error. They were recorded, not failed: check their work.")
    return _capped(lines) or ["- None recorded."]


def _receipts(records: list, projection: dict, terminal: dict) -> list[str]:
    payload = terminal["payload"]
    lines = [f"- Operation: `{one_line(projection.get('operation_ref'), 80)}`",
             f"- Journey: `{one_line(projection.get('journey_ref'), 80)}`",
             f"- Private trace: `{one_line(projection.get('trace_ref'), 80)}`, "
             f"{len(records)} records, "
             f"head `{records[-1]['record_sha256'] if records else 'none'}`"]
    if payload.get("checkpoint"):
        lines.append(f"- Ledger checkpoint: `{one_line(payload['checkpoint'], 80)}` "
                     f"(chain verified at run end: {payload.get('verified')})")
    verdict = payload.get("verdict")
    if isinstance(verdict, dict):
        lines.append(f"- Run verdict: accepted={verdict.get('accepted')}, "
                     f"chain_intact={verdict.get('chain_intact')}")
    return lines


def _capped(lines: list[str], unlisted: int = 0) -> list[str]:
    """At most MAX_LINES lines, then a count of what was left out and where."""
    rest = max(0, len(lines) - MAX_LINES)
    unlisted = unlisted if type(unlisted) is int and unlisted > 0 else 0
    parts = ([f"{rest} more in the trace"] if rest else []) + (
        [f"{unlisted} more not listed in the completion record"] if unlisted else [])
    return lines[:MAX_LINES] + ([f"- and {', and '.join(parts)}"] if parts else [])


def _section(title: str, lines: list[str], empty: str) -> str:
    return f"## {title}\n\n" + "\n".join(lines or [empty])


def handoff_markdown(records: list, projection: dict) -> str:
    """Render one run's trace as a Markdown brief for another agent."""
    from .gateway_completion_outcome import trace_workspace_root
    terminal = _terminal(records)
    payload = terminal["payload"]
    state, reason = projection.get("state", "unknown"), projection.get("reason")
    root, goal, final = trace_workspace_root(records), _goal(records), payload.get("final")
    outcome = _outcome(records, state)
    completion = outcome["completion"]
    report = payload.get("completion") if isinstance(payload.get("completion"), dict) else {}
    commands = [f"- {code(c, root, 160)}" for c in _commands(records)]
    steps = [f"{i}. {s}" for i, s in enumerate(_stated_steps(records, root), 1)]
    body = [
        f"# Handoff: {one_line(outbound(goal, root), 80) or 'Rowan run'}",
        "Exported from a recorded Rowan run so another agent can continue it. "
        "Nothing was re-run for this export. The marks below are the ones "
        "recorded when the run ended, checked against the run's trace, and the "
        "model's words are labelled as its words. Credentials and host paths "
        "found by pattern are replaced with markers.",
        _section("Goal", [quote(goal, root, max_chars=GOAL_CHARS)], ""),
        _section("Where it ended", _ended(state, reason, completion, outcome["budget"]), ""),
        _section("Deliverables", _deliverables(
            report, completion.get("status") == "recorded", root), "- None recorded."),
        _section("Commands run", _capped(commands), "- None."),
        _section("Steps the model stated (its words, not checked)", _capped(steps),
                 "- None recorded."),
        _section("Open items", _open_items(state, reason, report, completion, payload,
                                           root), ""),
        _section("Final answer (the model's words)",
                 [quote(final, root, max_chars=FINAL_CHARS)] if final else [],
                 "No final answer was recorded."),
        _section("Receipts", _receipts(records, projection, terminal), ""),
        "File contents are not included. Ask the owner for the workspace, or "
        "reproduce the deliverables and rerun their checks.",
    ]
    return "\n".join(safe_line(line) for line in "\n\n".join(body).split("\n")) + "\n"


def read_handoff(service, owner_ref: str, operation_ref: str) -> dict:
    """The owner's brief for one run, bound to the trace it was read from."""
    from .gateway_agent_trace import AgentTrace, TraceError
    from .gateway_operation import GatewayOperationError
    snapshot = service.snapshot(owner_ref, operation_ref)
    if snapshot.state not in _TERMINAL:
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
            "markdown": handoff_markdown(records, {**projection, "state": snapshot.state}),
            "does_not_prove": list(DOES_NOT_PROVE)}
