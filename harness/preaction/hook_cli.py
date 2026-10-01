"""hook_cli.py -- the external hook adapter for Claude Code and Codex.

`python -P -E -m harness.preaction.hook_cli <claude-code|codex> [flags]`, reads
one hook event as JSON on stdin and answers on stdout (and exit code). It fails
closed on its own: any error, unreadable input or a crossed internal deadline
yields an explicit stop (ask in an interactive Claude Code session, deny plus
exit 2 everywhere else), never a silent non-blocking exit. The internal
deadline sits well under the vendor hook timeout so the vendor's
non-blocking-on-timeout rule never decides the call.

Vendor contracts read 2026-10-01: exit 2 blocks; Claude Code honors
permissionDecision ask/deny/allow/defer; Codex parses but does not support ask,
so every Codex hold is a deny. The hook sends tool input and no reasoning, so
the judge's reasoning channel is off on this path.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

from . import records
from .contract import ALLOW, HOLD, ProposedCall, RunContext

CLIENTS = ("claude-code", "codex")
# Claude Code modes in which no person is asked: an "ask" there must not be
# relied on to reach a human, so a hold is a deny (docs read 2026-10-01).
_NO_PROMPT_MODES = ("bypassPermissions", "dontAsk")


def _interactive(client: str, event: dict) -> bool:
    mode = event.get("permission_mode")
    return client == "claude-code" and mode not in (None, "") and mode not in _NO_PROMPT_MODES


@dataclass
class Session:
    goal: str = ""


def _session_path(home, client, session_id) -> Path:
    safe = "".join(c for c in str(session_id) if c.isalnum() or c in "-_") or "none"
    return Path(home) / "sessions" / client / f"{safe}.json"


def load_session(home, client, session_id) -> Session:
    p = _session_path(home, client, session_id)
    if p.exists():
        return Session(goal=json.loads(p.read_text(encoding="utf-8")).get("goal", ""))
    return Session()


def _save_session(home, client, session_id, goal) -> None:
    p = _session_path(home, client, session_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"goal": goal}), encoding="utf-8")


def _tool_fields(event: dict) -> tuple:
    tool = event.get("tool_name", "")
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {"value": tool_input} if tool_input is not None else {}
    return tool, tool_input, event.get("tool_use_id", ""), event.get("session_id") or event.get("turn_id", "")


def _assess_event(home, client, event, hold_mode):
    """Run the monitor on one PreToolUse event. Returns the Gate."""
    from .core import Monitor
    tool, tool_input, use_id, session_id = _tool_fields(event)
    session = load_session(home, client, session_id)
    interactive = _interactive(client, event)
    mon = Monitor(home=home)
    call = ProposedCall(tool=tool, args=tool_input, harness=client, path_id="E11",
                        tool_use_id=use_id)
    ctx = RunContext(run_id=str(session_id) or "hook", goal=session.goal,
                     workspace=str(event.get("cwd", "")), interactive=interactive)
    # Parallel tool calls fire parallel hook processes; one lock per home keeps
    # the run state (counters, taint, rejections) from losing updates.
    from ..journey_lock import ExclusiveJourneyLock
    Path(home).mkdir(parents=True, exist_ok=True)
    with ExclusiveJourneyLock.acquire(Path(home) / ".gate.lock", 8.0):
        return mon.gate(call, ctx)


def _run_with_deadline(fn, deadline):
    box = {}

    def _call():
        try:
            box["r"] = fn()
        except Exception as exc:  # noqa: BLE001
            box["e"] = exc
    th = threading.Thread(target=_call, daemon=True)
    th.start()
    th.join(timeout=deadline)
    if th.is_alive():
        return None, TimeoutError("internal deadline")
    return box.get("r"), box.get("e")


def _emit(stdout, decision, reason=""):
    out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision}}
    if reason:
        out["hookSpecificOutput"]["permissionDecisionReason"] = reason
    stdout.write(json.dumps(out))


def _handle_pre(args, event, stdout, stderr) -> int:
    gate, err = _run_with_deadline(
        lambda: _assess_event(args.home, args.client, event, args.hold_mode), args.deadline)
    interactive = _interactive(args.client, event)
    if err is not None:
        reason = ("held: internal deadline reached; failing closed"
                  if isinstance(err, TimeoutError) else "held: monitor error; failing closed")
        if interactive and args.hold_mode == "ask":
            _emit(stdout, "ask", reason)
            return 0
        _emit(stdout, "deny", reason)
        stderr.write(reason)
        return 2
    if gate.verdict == ALLOW and gate.run:
        return 0                       # no decision: the harness's own permissions still apply
    reason = gate.agent_text
    if gate.verdict == HOLD and interactive and args.hold_mode == "ask":
        _emit(stdout, "ask", reason)
        return 0
    _emit(stdout, "deny", reason)
    stderr.write(reason)
    return 2


def _handle_post(args, event, stdout) -> int:
    tool, tool_input, use_id, session_id = _tool_fields(event)
    call = ProposedCall(tool=tool, args=tool_input)
    rec = records.post_record(harness=args.client, run_id=str(session_id), tool=tool,
                              tool_use_id=use_id, args_sha256=call.args_sha256(),
                              observed_at="")
    try:
        records.HoldStore(args.home).append(rec)
    except records.RecordWriteError:
        pass
    return 0


def _handle_prompt(args, event) -> int:
    session_id = event.get("session_id") or event.get("turn_id", "")
    goal = event.get("prompt") or event.get("user_prompt") or ""
    _save_session(args.home, args.client, session_id, str(goal))
    return 0


def main(argv=None, *, stdin=None, stdout=None, stderr=None) -> int:
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    stderr = stderr if stderr is not None else sys.stderr
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("client", choices=CLIENTS)
    parser.add_argument("--home", required=True)
    parser.add_argument("--post", action="store_true")
    parser.add_argument("--event", default="pre")
    parser.add_argument("--hold-mode", dest="hold_mode", default="ask", choices=("ask", "deny"))
    parser.add_argument("--deadline", type=float, default=10.0)
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        stderr.write("held: bad hook invocation; failing closed")
        return 2
    fail_closed_exit = 2
    try:
        event = json.loads(stdin.read())
        if not isinstance(event, dict):
            raise ValueError("event is not an object")
    except Exception:  # noqa: BLE001 -- unreadable input is never a pass
        # An unreadable event names no permission mode, so nobody is known to
        # be asked: deny plus exit 2, never an ask that might not reach a human.
        _emit(stdout, "deny", "held: unreadable hook event; failing closed")
        stderr.write("held: unreadable hook event; failing closed")
        return fail_closed_exit
    if args.event == "prompt" or event.get("hook_event_name") == "UserPromptSubmit":
        return _handle_prompt(args, event)
    if args.post or event.get("hook_event_name") == "PostToolUse":
        return _handle_post(args, event, stdout)
    return _handle_pre(args, event, stdout, stderr)


def entry(argv=None, *, stdin=None, stdout=None, stderr=None) -> int:
    """The process entry point. Claude Code and Codex treat every exit code but
    2 as non-blocking, so an unexpected crash (exit 1) would let the call run.
    Anything main() does not handle becomes exit 2 here."""
    err = stderr if stderr is not None else sys.stderr
    try:
        return main(argv, stdin=stdin, stdout=stdout, stderr=err)
    except BaseException as exc:  # noqa: BLE001 -- every escape is a block
        try:
            err.write(f"held: monitor crashed ({type(exc).__name__}); failing closed")
        except Exception:  # noqa: BLE001
            pass
        return 2


if __name__ == "__main__":
    raise SystemExit(entry())
