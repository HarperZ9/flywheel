"""Agentic loop: model text-tool calls, gated execution, witnessed ledger."""
from __future__ import annotations

import json

from . import integrity, tool_receipts
from .acceptance_criteria import all_pass, apply_oracle_result, failing, summary
from .local_session import SessionLedger
from .local_tools import TOOLS_SYSTEM, ToolExecutor, parse_tool_calls
from .structured_finalizer import finalized_candidate_text


def _edit_fingerprint(name, args, res, executor) -> "dict | None":
    """For a mutating tool, the post-edit content hash of the target path(s),
    so the receipt binds this edit to a specific file state. Best-effort:
    an unreadable target yields no fingerprint, never a fake one."""
    import hashlib
    import os
    if name not in ("write_file", "edit_file", "apply_patch"):
        return None
    root = getattr(executor, "root", None)
    if not root:
        return None
    paths = []
    if name in ("write_file", "edit_file") and args.get("path"):
        paths = [str(args["path"])]
    elif name == "apply_patch":
        patch = str(args.get("patch") or args.get("diff") or "")
        paths = [ln[6:].strip() for ln in patch.splitlines()
                 if ln.startswith("+++ b/")]
    files = {}
    for p in paths:
        try:
            data = open(os.path.join(root, p), "rb").read()
            files[p] = hashlib.sha256(data).hexdigest()
        except OSError:
            continue
    return {"edited": files} if files else None


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
              canaries: "list | None" = None, on_event=None, criteria: "list | None" = None,
              budget_note: bool = False, finalize_candidate=None) -> dict:
    """Run the goal to completion (or max_steps). Returns the final answer, the
    step count, and the ledger checkpoint + verify verdict.

    With `test_cmd`, the loop is a TEST-REPAIR loop: when the model believes it is
    done, the test command is run and, if it fails, the failure is fed back and
    the model keeps working until the tests pass (or steps run out). The result
    then carries `tests_pass`, and the whole edit->test->repair trajectory is
    witnessed in the ledger -- a provable "made the tests green".

    With `criteria` (an acceptance_criteria.new_criteria() list), the loop will
    not report done while any criterion is still FAILING: at the point it would
    finish, the failing ids are handed back as the next message instead, and the
    check is witnessed as a "criteria" ledger entry. Nothing here flips a
    criterion: only apply_oracle_result does, either by a caller directly or,
    when `test_cmd` and a criterion registered to oracle "test_cmd" are both
    present, by this loop applying that test run's outcome. `max_steps` is the
    ultimate backstop: it still ends the run even with criteria unmet, honestly
    (never reports accepted) rather than looping forever.

    `budget_note` is opt-in and only states the remaining step count; `max_steps`
    enforces it. `finalize_candidate` is opt-in and only runs at eligible no-call
    done boundaries after the rescue parser and criteria/test gates."""
    ledger = ledger if ledger is not None else SessionLedger()
    # Start the run's byte-witness chain, and its receipt chain when one is set.
    if hasattr(executor, "init_receipt_chain"):
        run_id = f"run-{ledger.checkpoint()[:12]}" if ledger.entries else f"run-{id(executor):x}"
        executor.init_receipt_chain(run_id)

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
    last_test_ok = None            # the most recent real test_cmd outcome, if any
    for step in range(1, max_steps + 1):
        to_send = message
        if budget_note:
            remaining = max_steps - step + 1
            budget_line = f"[budget] step {step} of {max_steps}, {remaining} remaining."
            ledger.append("budget", budget_line,
                          {"step": step, "max_steps": max_steps, "remaining": remaining})
            _emit(type="budget", step=step, max_steps=max_steps, remaining=remaining)
            to_send = f"{budget_line}\n\n{message}"
        resp = agent.send(to_send)
        text = resp["content"][0]["text"] if resp.get("content") else ""
        ledger.append("assistant", text, {
            "backend": resp.get("backend"),
            "receipt": resp.get("x_receipt", {}).get("receipt_id")})
        _emit(type="assistant", step=step, text=text)

        from .tool_rescue import rescue_tool_calls
        calls, repairs = rescue_tool_calls(text, with_preamble=True)
        for rep in repairs:
            ledger.append("tool_rescue", json.dumps(rep, sort_keys=True))
            _emit(type="tool_rescue", transform=rep["transform"])
        if not calls:
            if not test_cmd:
                done, feedback = _refuse_if_failing(
                    criteria, text, step, ledger, system=agent.system, goal=goal,
                    agent=agent, finalize_candidate=finalize_candidate,
                    candidate_state="eligible_no_test_no_criteria", emit=_emit)
                if done is not None:
                    return done
                message = feedback
                continue
            res = executor.execute("run", {"cmd": test_cmd})
            last_test_ok = res.ok
            ledger.append("tool_call", f"run {json.dumps({'cmd': test_cmd}, sort_keys=True)}")
            ledger.append("tool_result", res.output, _result_meta("run", res, sign_key, {"gate": "test"}))
            _emit(type="tool_result", name="run", ok=res.ok, output=res.output[:500])
            if criteria is not None:
                for cid in [c["id"] for c in criteria if c["oracle"] == "test_cmd"]:
                    rec = apply_oracle_result(criteria, cid, "test_cmd", res.ok,
                                              evidence=res.output[:500])
                    ledger.append("criteria", json.dumps(rec, sort_keys=True),
                                  {"flip": True, "oracle": "test_cmd"})
            if res.output.startswith("[gate]"):
                return _done(text, step, ledger, tests_pass=False,
                             note="test gate set but exec is disabled (pass --allow-exec)",
                             system=agent.system, goal=goal, criteria=criteria)
            if res.ok:
                done, feedback = _refuse_if_failing(
                    criteria, text, step, ledger, tests_pass=True,
                    system=agent.system, goal=goal, agent=agent,
                    finalize_candidate=finalize_candidate,
                    candidate_state="eligible_test_passed", emit=_emit)
                if done is not None:
                    return done
                message = feedback
                continue
            message = (f"The tests still FAIL:\n{res.output}\n\nFix the root cause and "
                       "continue; do not give a final answer until the tests pass.")
            continue

        observations = []
        for name, args, preamble in calls:
            rationale = None
            if preamble:
                rationale = {
                    "stated_intent": preamble[:500],
                    "options_considered": [],
                    "chosen_option": name,
                    "confidence": "unknown",
                }
            res = executor.execute(name, args, rationale=rationale)
            ledger.append("tool_call", f"{name} {json.dumps(args, sort_keys=True)}")
            # a mutating tool's receipt carries the post-edit file hash, so
            # a stranger can bind this specific edit to a specific file state
            extra = _edit_fingerprint(name, args, res, executor) \
                if res.ok else None
            ledger.append("tool_result", res.output,
                          _result_meta(name, res, sign_key, extra))
            _emit(type="tool_call", name=name, args=args)
            _emit(type="tool_result", name=name, ok=res.ok, output=res.output[:500])
            # canary tripwire: a decoy resource surfacing in a tool output is a
            # HARD access signal (our detection, not the model refusing).
            # Contain the run and stop; do not trust the model to have stopped.
            if canaries:
                from .canary_tripwire import scan_for_canary
                hit = scan_for_canary(res.output, canaries)
                if hit is not None:
                    ledger.append("canary_trip", json.dumps(
                        {"label": hit["label"], "tool": name}, sort_keys=True))
                    _emit(type="canary_trip", label=hit["label"], tool=name)
                    return _done("[contained] a canary (decoy resource) was "
                                 f"read via {name}; the run was stopped by "
                                 "the tripwire", step, ledger, tests_pass=False,
                                 note=f"canary '{hit['label']}' tripped; "
                                      "contain and investigate",
                                 system=agent.system, goal=goal, criteria=criteria)
            observations.append(f"TOOL {name} -> {'ok' if res.ok else 'FAIL'}:\n{res.output}")

        message = ("TOOL RESULTS:\n" + "\n\n".join(observations) +
                   "\n\nContinue if you need more tools, otherwise give the final "
                   "answer with no TOOL line.")

    # A configured test_cmd that never ran yields False, not None: an
    # unwitnessed run must not read as neutral. The note keeps it separable.
    unrun = last_test_ok is None and bool(test_cmd)
    return _done("[max_steps reached without a final answer]", max_steps, ledger,
                 tests_pass=(last_test_ok if last_test_ok is not None
                             else (False if test_cmd else None)),
                 note=("step budget exhausted; the test command never ran, so "
                       "this is unwitnessed, not an observed failure") if unrun else "",
                 system=agent.system, goal=goal, criteria=criteria)


def _refuse_if_failing(criteria, text, step, ledger, *, tests_pass=None, note="",
                       system="", goal="", agent=None, finalize_candidate=None,
                       candidate_state="", emit=None) -> tuple:
    """At the point the loop would report done: witness the check as a
    "criteria" ledger entry, and if `criteria` is given and any criterion is
    still FAILING, refuse -- return the failing ids as the next message
    instead of finishing. Returns (done_result, None) when the run may
    finish, or (None, next_message) when it must keep going. criteria=None
    reproduces today's behavior exactly: always finishes here, no entry
    appended (there is nothing to check)."""
    if criteria is None:
        text = finalized_candidate_text(
            finalize_candidate, candidate_text=text, candidate_state=candidate_state,
            step=step, ledger=ledger, agent=agent, system=system, goal=goal,
            tests_pass=tests_pass, emit=emit)
        return _done(text, step, ledger, tests_pass=tests_pass, note=note,
                     system=system, goal=goal), None
    ids = failing(criteria)
    ledger.append("criteria",
                  json.dumps({"failing_ids": ids, "checked_at_step": step}, sort_keys=True),
                  {"failing": len(ids), "total": len(criteria)})
    if ids:
        feedback = ("Acceptance criteria still FAILING: " + ", ".join(ids) +
                    ". Continue working; do not give a final answer until "
                    "every criterion passes.")
        return None, feedback
    text = finalized_candidate_text(
        finalize_candidate, candidate_text=text,
        candidate_state=candidate_state or "eligible_criteria_satisfied",
        step=step, ledger=ledger, agent=agent, system=system, goal=goal,
        tests_pass=tests_pass, emit=emit)
    return _done(text, step, ledger, tests_pass=tests_pass, note=note,
                 system=system, goal=goal, criteria=criteria), None


def _environment() -> dict:
    """Runtime identity pinned into every run doc (landscape import 2:
    environments-as-code, receipts-first). Named, so a re-run can state
    whether it matched."""
    import platform
    import sys
    return {"python": sys.version.split()[0],
            "platform": platform.platform(),
            "machine": platform.machine()}


def _done(final: str, steps: int, ledger: SessionLedger, *, tests_pass=None,
          note="", system: str = "", goal: str = "", criteria=None) -> dict:
    from .context_manifest import context_manifest
    from .risk_review import risk_review
    from .run_review import run_review
    out = {"final": final, "steps": steps,
           "checkpoint": ledger.checkpoint(), "verified": ledger.verify(),
           "entries": len(ledger.entries), "ledger": ledger,
           "review": run_review(ledger.entries),
           "context_manifest": context_manifest(
               ledger.entries, system=system, goal=goal),
           "risk_review": risk_review(ledger.entries),
           "environment": _environment()}
    out["integrity"] = integrity.integrity_report(integrity.trajectory_integrity(ledger))
    if tests_pass is not None:
        out["tests_pass"] = tests_pass
        # a pass is only trusted if the trajectory did not tamper with the check
        out["tests_pass_trusted"] = bool(tests_pass) and out["integrity"]["clean"]
    if note:
        out["note"] = note
    if criteria is not None:
        out["criteria"] = summary(criteria)
        out["accepted"] = all_pass(criteria)
        out["accepted_trusted"] = bool(out["accepted"]) and out["integrity"]["clean"]
    return out
