"""local_loop.py — the agentic loop: local model + gated tools + witnessed ledger.

This is what turns the chat client into an actual local coding agent. The model
proposes tool calls in the text protocol, the executor runs them under the gate,
observations are fed back, and the whole trajectory (turns + tool calls +
results) is appended to a hash-chained SessionLedger. The loop terminates when
the model stops emitting TOOL lines (final answer) or max_steps is hit — always
returning a re-verifiable checkpoint.
"""
from __future__ import annotations

import json

from . import integrity, tool_receipts
from .local_session import SessionLedger
from .local_tools import TOOLS_SYSTEM, ToolExecutor, parse_tool_calls


def _result_meta(name, res, sign_key, extra=None) -> dict:
    meta = {"tool": name, "ok": res.ok}
    if extra:
        meta.update(extra)
    if sign_key is not None:           # per-run HMAC: authenticity of each tool call
        meta["sig"] = tool_receipts.sign_result(sign_key, res)
    return meta


def run_agent(agent, goal: str, executor: ToolExecutor,
              ledger: "SessionLedger | None" = None, *, max_steps: int = 6,
              test_cmd: "str | None" = None, sign_key: "bytes | None" = None,
              on_event=None) -> dict:
    """Run the goal to completion (or max_steps). Returns the final answer, the
    step count, and the ledger checkpoint + verify verdict.

    With `test_cmd`, the loop is a TEST-REPAIR loop: when the model believes it is
    done, the test command is run and, if it fails, the failure is fed back and
    the model keeps working until the tests pass (or steps run out). The result
    then carries `tests_pass`, and the whole edit->test->repair trajectory is
    witnessed in the ledger — a provable "made the tests green"."""
    ledger = ledger if ledger is not None else SessionLedger()

    def _emit(**e):                                  # stream loop progress; never let it break the loop
        if on_event is not None:
            try:
                on_event(e)
            except Exception:
                pass

    if TOOLS_SYSTEM not in agent.system:
        agent.system = agent.system + "\n\n" + TOOLS_SYSTEM
    ext_sys = executor.external_tools_system() if hasattr(executor, "external_tools_system") else ""
    if ext_sys and ext_sys not in agent.system:
        agent.system = agent.system + "\n\n" + ext_sys

    ledger.append("user", goal)
    message = goal
    for step in range(1, max_steps + 1):
        resp = agent.send(message)
        text = resp["content"][0]["text"] if resp.get("content") else ""
        ledger.append("assistant", text, {
            "backend": resp.get("backend"),
            "receipt": resp.get("x_receipt", {}).get("receipt_id")})
        _emit(type="assistant", step=step, text=text)

        calls = parse_tool_calls(text)
        if not calls:
            if not test_cmd:
                return _done(text, step, ledger,
                             system=agent.system, goal=goal)
            res = executor.execute("run", {"cmd": test_cmd})
            ledger.append("tool_call", f"run {json.dumps({'cmd': test_cmd}, sort_keys=True)}")
            ledger.append("tool_result", res.output, _result_meta("run", res, sign_key, {"gate": "test"}))
            _emit(type="tool_result", name="run", ok=res.ok, output=res.output[:500])
            if res.output.startswith("[gate]"):
                return _done(text, step, ledger, tests_pass=False,
                             note="test gate set but exec is disabled (pass --allow-exec)",
                             system=agent.system, goal=goal)
            if res.ok:
                return _done(text, step, ledger, tests_pass=True,
                             system=agent.system, goal=goal)
            message = (f"The tests still FAIL:\n{res.output}\n\nFix the root cause and "
                       "continue; do not give a final answer until the tests pass.")
            continue

        observations = []
        for name, args in calls:
            res = executor.execute(name, args)
            ledger.append("tool_call", f"{name} {json.dumps(args, sort_keys=True)}")
            ledger.append("tool_result", res.output, _result_meta(name, res, sign_key))
            _emit(type="tool_call", name=name, args=args)
            _emit(type="tool_result", name=name, ok=res.ok, output=res.output[:500])
            observations.append(f"TOOL {name} -> {'ok' if res.ok else 'FAIL'}:\n{res.output}")

        message = ("TOOL RESULTS:\n" + "\n\n".join(observations) +
                   "\n\nContinue if you need more tools, otherwise give the final "
                   "answer with no TOOL line.")

    return _done("[max_steps reached without a final answer]", max_steps, ledger,
                 tests_pass=(False if test_cmd else None),
                 system=agent.system, goal=goal)


def _done(final: str, steps: int, ledger: SessionLedger, *, tests_pass=None,
          note="", system: str = "", goal: str = "") -> dict:
    from .context_manifest import context_manifest
    from .run_review import run_review
    out = {"final": final, "steps": steps,
           "checkpoint": ledger.checkpoint(), "verified": ledger.verify(),
           "entries": len(ledger.entries), "ledger": ledger,
           # the reviewability projection: what a senior reviewer checks
           # first, derived from the witnessed ledger, shipped with the run
           "review": run_review(ledger.entries),
           # the window manifest: what the model actually saw, replayable
           "context_manifest": context_manifest(
               ledger.entries, system=system, goal=goal)}
    # Trajectory-integrity verdict: did the agent edit the file that grades it, or
    # write test-neutralizing code? Surfaced re-checkably so a tampered "green" is
    # visible, not silently accepted (reward-hacking guard, keeps the C2 invariant).
    out["integrity"] = integrity.integrity_report(integrity.trajectory_integrity(ledger))
    if tests_pass is not None:
        out["tests_pass"] = tests_pass
        # a pass is only trusted if the trajectory did not tamper with the check
        out["tests_pass_trusted"] = bool(tests_pass) and out["integrity"]["clean"]
    if note:
        out["note"] = note
    return out
