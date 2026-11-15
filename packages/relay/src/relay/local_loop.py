"""local_loop.py — the agentic loop: local model + gated tools + witnessed ledger.

This is what turns the chat client into an actual local coding agent. The model
proposes tool calls in the text protocol, the executor runs them under the gate,
observations are fed back, and the whole trajectory (turns + tool calls +
results) is appended to a hash-chained SessionLedger. The loop terminates when
the model stops emitting TOOL lines (final answer) or max_steps is hit — always
returning a re-verifiable checkpoint, and recording a backend death mid-run as an
honest error entry rather than an uncaught traceback.
"""
from __future__ import annotations

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor

from .local_agent import BackendError
from .local_session import SessionLedger
from .approvals import call_hash, is_mutating
from .local_tools import (TOOLS_SYSTEM, ToolExecutor, ToolResult, edited_targets,
                          parse_tool_calls)
from .messages_api import recompute_receipt_id

_CHECK_TIMEOUT = 600   # an acceptance check (a test/build suite) may be slow

# Side-effect-free tools: running them concurrently cannot race, so a turn that
# emits several of them (read three files at once) is parallelized. Any mutating or
# executing tool in the batch forces the whole turn to run sequentially and in order.
READ_ONLY_TOOLS = frozenset({"read_file", "list_dir", "repo_map"})


def _persist_progress_if_available(ledger) -> None:
    """Ask async run ledgers to durably snapshot partial progress.

    Plain SessionLedger.checkpoint() returns a chain digest, so durable run
    persistence is intentionally a separate opt-in method.
    """
    persist = getattr(ledger, "persist_checkpoint", None)
    if callable(persist):
        persist()


def _execute_calls(executor, calls: list) -> list:
    """Execute a turn's tool calls, returning results in the ORIGINAL call order.
    All-reads batches run in a thread pool (no side effects, no races); a batch with
    any write/exec runs sequentially, so ordering and the gate are never weakened."""
    if len(calls) > 1 and all(name in READ_ONLY_TOOLS for name, _ in calls):
        with ThreadPoolExecutor(max_workers=min(len(calls), 8)) as pool:
            return list(pool.map(lambda call: executor.execute(call[0], call[1]), calls))
    return [executor.execute(name, args) for name, args in calls]


def _approve_calls(approve, calls: list, ledger) -> list:
    """Record an allow/deny approval for each mutating call before it runs, bound to
    the call's content hash. Returns an allow mask; read-only calls are always allowed
    and get no entry, so a read-only turn is unchanged."""
    mask = []
    for name, args in calls:
        if not is_mutating(name):
            mask.append(True)
            continue
        allow = bool(approve(name, args))
        ledger.append("approval", call_hash(name, args),
                      {"tool": name, "decision": "allow" if allow else "deny"})
        mask.append(allow)
    return mask


def _execute_masked(executor, calls: list, mask: list) -> list:
    """Execute only the approved calls (via the same read-parallel path) and slot a
    rejection result in for each denied call, preserving original order."""
    approved = iter(_execute_calls(executor, [c for c, ok in zip(calls, mask) if ok]))
    out = []
    for (name, args), ok in zip(calls, mask):
        out.append(next(approved) if ok else
                   ToolResult(name, args, False, "[approval] operator rejected this call"))
    return out


def _maybe_compact(agent, budget: int, ledger) -> None:
    """Fold the agent's growing history to fit `budget` and WITNESS the fold on the
    ledger. The untruncated trajectory stays on the ledger; only the prompt shrinks,
    and the receipt binds the folded span + summary hashes so the fold is re-checkable."""
    from .compaction import compact
    history = getattr(agent, "history", None)
    if not history:
        return
    res = compact(history, token_budget=budget)
    if res.compacted:
        agent.history = res.messages
        ledger.append("compaction", res.receipt["summary_sha256"], res.receipt)


def run_agent(agent, goal: str, executor: ToolExecutor,
              ledger: "SessionLedger | None" = None, *, max_steps: int = 6,
              check: "str | None" = None, test_cmd: "str | None" = None,
              approve=None, compact_budget: int = 0) -> dict:
    """Run the goal to completion (or max_steps). Returns the final answer, the
    step count, and the ledger checkpoint + verdict.

    ``check`` is an operator-supplied acceptance command (e.g. ``pytest -q``) run
    ONCE when the agent produces a final answer; the run is ACCEPTED only if it
    passes. It carries operator authority (the operator chose it), so it runs
    outside the model's tool gate; it is never a call the model can emit or steer.

    ``test_cmd`` is the same idea as a REPAIR LOOP: when the model believes it is
    done, the command runs and, if it fails, the failure is fed back and the model
    keeps working until it passes (or steps run out) — a provable "made the tests
    green". It shares ``check``'s rich verdict (verified/accepted/integrity/review),
    so both surfaces report the same way; pass at most one of the two."""
    ledger = ledger if ledger is not None else SessionLedger()
    # Resume: a non-empty ledger passed in is a saved session being continued. Seed
    # the model's history from its transcript so the run picks up in context, and the
    # new turns extend the same hash chain, so the resumed session stays re-verifiable.
    if ledger.entries and hasattr(agent, "history"):
        agent.history = [dict(m) for m in ledger.transcript()]
    if TOOLS_SYSTEM not in agent.system:
        agent.system = agent.system + "\n\n" + TOOLS_SYSTEM

    ledger.append("user", goal)
    message = goal
    for step in range(1, max_steps + 1):
        if compact_budget:
            _maybe_compact(agent, compact_budget, ledger)   # opt-in; keeps the prompt in-budget
        try:
            resp = agent.send(message)
        except BackendError as e:
            # every backend died mid-run: witness the failure (with the partial
            # work already on the chain) instead of letting it vanish as a traceback.
            ledger.append("error", str(e), {"step": step})
            _persist_progress_if_available(ledger)
            return _done(f"[backend failure at step {step}] {e}", step, ledger,
                         final_answer=False)
        text = resp["content"][0]["text"] if resp.get("content") else ""
        meta = {"backend": resp.get("backend"),
                "receipt": resp.get("x_receipt", {})}   # the FULL receipt, re-derivable
        if resp.get("failover"):
            meta["failover"] = resp["failover"]         # a failed earlier tier is bound in
        ledger.append("assistant", text, meta)
        _persist_progress_if_available(ledger)

        calls = parse_tool_calls(text)
        if not calls:
            if test_cmd:
                res = executor.execute("run", {"cmd": test_cmd})
                ledger.append("tool_call", f"run {json.dumps({'cmd': test_cmd}, sort_keys=True)}")
                ledger.append("tool_result", res.output, {"tool": "run", "ok": res.ok, "gate": "test"})
                _persist_progress_if_available(ledger)
                if res.output.startswith("[gate]"):
                    return _done(text, step, ledger, final_answer=True, check_passed=False,
                                 note="test gate set but exec is disabled (pass --allow-exec)")
                if res.ok:
                    return _done(text, step, ledger, final_answer=True, check_passed=True)
                message = (f"The tests still FAIL:\n{res.output}\n\nFix the root cause and "
                           "continue; do not give a final answer until the tests pass.")
                continue
            return _done(text, step, ledger, final_answer=True,
                         check_passed=_run_acceptance(check, executor, ledger))

        observations = []
        if approve is None:
            results = _execute_calls(executor, calls)     # headless: unchanged path
        else:
            results = _execute_masked(executor, calls, _approve_calls(approve, calls, ledger))
        for (name, args), res in zip(calls, results):
            ledger.append("tool_call", f"{name} {json.dumps(args, sort_keys=True)}")
            ledger.append("tool_result", res.output, {"tool": name, "ok": res.ok})
            observations.append(f"TOOL {name} -> {'ok' if res.ok else 'FAIL'}:\n{res.output}")

        message = ("TOOL RESULTS:\n" + "\n\n".join(observations) +
                   "\n\nContinue if you need more tools, otherwise give the final "
                   "answer with no TOOL line.")
        ledger.append("user", message)   # the continuation prompt the model actually sees next
        _persist_progress_if_available(ledger)

    return _done("[max_steps reached without a final answer]", max_steps, ledger,
                 final_answer=False,
                 check_passed=(False if test_cmd else None))


def _run_acceptance(check: "str | None", executor: ToolExecutor,
                    ledger: SessionLedger) -> "bool | None":
    """Run the operator's acceptance command in the executor's root and witness the
    result on the ledger. Returns True/False, or None when no check was requested.
    A timeout is its own honest failure, not a silent pass."""
    if not check:
        return None
    try:
        if executor.runner is not None:            # injected for tests
            ok, out = executor.runner(check, executor.root)
        else:
            from .child_env import shell_env
            proc = subprocess.run(check, shell=True, cwd=executor.root,
                                  env=shell_env(cwd=executor.root),
                                  capture_output=True, text=True, timeout=_CHECK_TIMEOUT)
            ok = proc.returncode == 0
            out = f"[exit {proc.returncode}]\n{(proc.stdout or '') + (proc.stderr or '')}"
    except subprocess.TimeoutExpired:
        ok, out = False, f"[check timeout after {_CHECK_TIMEOUT}s]"
    except Exception as e:
        # a check that cannot even run (bad cwd, a raising runner) is a FAILED
        # acceptance, witnessed like any other, never a traceback that discards the
        # checkpoint the loop built.
        ok, out = False, f"[check errored: {type(e).__name__}: {e}]"
    ledger.append("check", str(out)[:4000], {"cmd": check, "ok": bool(ok)})
    return bool(ok)


def _done(final: str, steps: int, ledger: SessionLedger, *, final_answer: bool,
          check_passed: "bool | None" = None, note: str = "") -> dict:
    from .approvals import approval_verdict
    from .claim_grounding import ground_final_answer
    from .integrity import integrity_report, trajectory_integrity
    from .intent_audit import audit_intent
    from .review import risk_review, run_review
    chain_ok = ledger.verify()
    receipts_ok = verify_receipts(ledger)
    verified = chain_ok and receipts_ok and final_answer
    integrity = integrity_report(trajectory_integrity(ledger))
    # A passing check is TRUSTED only if the trajectory did not tamper with the thing
    # that grades it (edit the test file, inject a skip/exit). No check ran -> there was
    # nothing to game, so trust is not in question.
    check_trusted = check_passed is not True or integrity["clean"]
    return {"final": final, "steps": steps,
            "checkpoint": ledger.checkpoint(),
            "chain_ok": chain_ok,          # in-memory chain integrity (structural)
            "receipts_ok": receipts_ok,    # every per-turn receipt id re-derives from stored fields
            "final_answer": final_answer,  # a real final answer was produced (not max_steps / failure)
            # honest composite, NOT the self-confirming in-memory check alone: a
            # run only "verifies" if the chain holds, the receipts re-derive, AND an
            # answer was actually produced.
            "verified": verified,
            "check_passed": check_passed,  # the acceptance check's verdict, or None if none was run
            "integrity": integrity,        # reward-hacking flags over the witnessed edit set
            "check_trusted": check_trusted,  # a pass survives only if the grader was not tampered with
            # the reviewability projection: what a senior reviewer checks first, and
            # per-edit risk tiers, both derived from the witnessed ledger (facts, not prose)
            "review": run_review(ledger.entries),
            "risk": risk_review(ledger.entries),
            # intent/scope audit (ported from agent-audit): claimed_history runs on
            # every run and flags reasoning that claims work the ledger never did.
            "intent_audit": audit_intent(ledger),
            # claim grounding: is the FINAL ANSWER entailed by the witnessed ledger?
            # GROUNDED / UNGROUNDED / REFUTED / UNVERIFIABLE -- a lying summary over an
            # intact chain is caught here.
            "grounded": ground_final_answer(ledger)["verdict"],
            # per-step approval: were the mutating steps gated by a decision bound to
            # their exact bytes? GATED / UNGATED / NOT_GATED (no approvals recorded).
            "approved": approval_verdict(ledger),
            # ACCEPTED = a verified trajectory whose acceptance check did not fail AND
            # whose pass was not gamed by tampering with the check. No check -> collapses
            # to `verified`; a failed OR tampered pass is never accepted.
            "accepted": verified and check_passed is not False and check_trusted,
            "entries": len(ledger.entries), "ledger": ledger,
            **({"note": note} if note else {})}


def verify_receipts(ledger: SessionLedger) -> bool:
    """Re-derive every stored per-turn receipt_id from its own recorded fields.
    Fail-closed: an assistant turn that claims a receipt but lacks the fields to
    re-derive it is NOT accepted — an opaque id no stranger can re-check is
    unverifiable, never a pass."""
    for e in ledger.entries:
        if e.kind != "assistant":
            continue
        rec = e.meta.get("receipt")
        if not rec:
            continue
        if not isinstance(rec, dict) or "receipt_id" not in rec:
            return False
        try:
            if recompute_receipt_id(rec) != rec["receipt_id"]:
                return False
        except (KeyError, TypeError):
            return False
    return True


def witnessed_edit_paths(ledger: SessionLedger) -> list:
    """Paths the ledger recorded as write_file/edit_file targets — the edit set a
    commit is allowed to bind. A file written another way (shell redirection via
    `run`) is not recorded as content here, so it is never attributed to the
    witnessed trajectory."""
    paths: list = []
    for e in ledger.entries:
        if e.kind != "tool_call":
            continue
        name, _, rest = e.content.partition(" ")
        try:
            args = json.loads(rest)
        except json.JSONDecodeError:
            continue
        if not isinstance(args, dict):
            continue
        for p, _new in edited_targets(name, args):
            if p not in paths:
                paths.append(p)
    return paths
