"""workflows.py -- staged agentic runs with a chained receipt, over ANY endpoint.

A workflow is an ordered list of steps run through the same gated router
agent every surface uses. Each step's summary (final excerpt, ledger
checkpoint, integrity verdict) is folded into a chain hash, so the whole
run carries one re-checkable receipt. Steps can FAIL and the run says so;
a verify step without an exec grant reports UNVERIFIABLE instead of
pretending. Because the endpoint is a runtime argument, the same staged
discipline runs over any provider or model generation in the roster."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from .endpoint_registry import ProviderPermissionError
from .router_agent import run_router_agent

WORKFLOWS = {
    "code-change": {
        "description": "Plan the smallest correct change, apply it under the "
                       "gate, prove it with the test command.",
        "steps": [
            {"name": "plan", "kind": "agent", "max_steps": 4,
             "goal": "Plan the smallest correct change for: {goal}\n"
                     "List the files to touch and the check that proves it. "
                     "Do not edit anything yet."},
            {"name": "apply", "kind": "agent", "max_steps": 8,
             "goal": "Apply this plan using the tools:\n{prev}\n\nGoal: {goal}"},
            {"name": "verify", "kind": "verify"},
        ],
    },
    "research-brief": {
        "description": "Draft a dense sourced brief, then adversarially "
                       "review it for unsupported claims.",
        "steps": [
            {"name": "draft", "kind": "agent", "max_steps": 6,
             "goal": "Research and draft a dense, sourced brief on: {goal}\n"
                     "State unknowns honestly; never pad."},
            {"name": "critique", "kind": "agent", "max_steps": 3,
             "goal": "Adversarially review this brief. List every claim a "
                     "reader could not check from the cited sources, and why:\n{prev}"},
        ],
    },
    "design-schematic": {
        "description": "Write a precise component spec, then render it as a "
                       "schematic.",
        "steps": [
            {"name": "spec", "kind": "agent", "max_steps": 4,
             "goal": "Write a precise component spec for: {goal}\n"
                     "Inputs, outputs, invariants, failure modes."},
            {"name": "schematic", "kind": "agent", "max_steps": 4,
             "goal": "Render this spec as a plain-text schematic (boxes and "
                     "arrows) followed by a minimal SVG sketch:\n{prev}"},
        ],
    },
    "verify-claim": {
        "description": "Gather checkable evidence for and against a claim, "
                       "then state MATCH, DRIFT, or UNVERIFIABLE.",
        "steps": [
            {"name": "evidence", "kind": "agent", "max_steps": 5,
             "goal": "Gather checkable evidence for and against: {goal}\n"
                     "Cite only what a verifier could re-run or re-read."},
            {"name": "verdict", "kind": "agent", "max_steps": 2,
             "goal": "From this evidence alone, state MATCH, DRIFT, or "
                     "UNVERIFIABLE with the single strongest reason:\n{prev}"},
        ],
    },
}


def workflow_roster(run_root: "Path | str | None" = None) -> dict:
    """Workflow definitions plus recent persisted runs (newest first)."""
    defs = [{"name": k, "description": v["description"],
             "steps": [{"name": s["name"], "kind": s["kind"]} for s in v["steps"]]}
            for k, v in WORKFLOWS.items()]
    runs = []
    if run_root:
        d = Path(run_root) / "workflow_runs"
        if d.is_dir():
            files = sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime,
                           reverse=True)[:20]
            for p in files:
                try:
                    doc = json.loads(p.read_text(encoding="utf-8"))
                    row = {k: doc.get(k) for k in
                           ("workflow", "endpoint", "status", "chain_hash",
                            "started", "goal_excerpt")}
                    # re-verify the stored chain rather than trusting it: a
                    # hand-flipped status or rewritten steps is served as
                    # TAMPERED, never as a legitimate prior run
                    recomputed = recompute_chain(doc)
                    row["chain_ok"] = recomputed == doc.get("chain_hash")
                    if not row["chain_ok"]:
                        row["status"] = "TAMPERED"
                    if p.stem != str(doc.get("chain_hash", ""))[:16]:
                        row["chain_ok"] = False
                        row["status"] = "TAMPERED"
                    runs.append(row)
                except Exception:
                    runs.append({"workflow": p.stem, "status": "UNREADABLE"})
    return {"schema": "flywheel.workflows/v1", "workflows": defs, "runs": runs}


def workflow_run_detail(run_root, prefix: str) -> dict:
    """The full stored per-stage trace of one run, chain-reverified at read
    time exactly like the roster: a rewritten step or a renamed receipt is
    served as TAMPERED, never as a legitimate trace."""
    prefix = (prefix or "").strip().lower()
    if len(prefix) < 4:
        return {"error": "give at least 4 chain-hash characters"}
    d = Path(run_root) / "workflow_runs"
    matches = sorted(d.glob(f"{prefix[:16]}*.json")) if d.is_dir() else []
    if not matches:
        return {"error": f"no workflow run matching '{prefix[:16]}'"}
    try:
        doc = json.loads(matches[0].read_text(encoding="utf-8"))
    except Exception:
        return {"error": f"receipt unreadable: {matches[0].name}"}
    ok = (recompute_chain(doc) == doc.get("chain_hash")
          and matches[0].stem == str(doc.get("chain_hash", ""))[:16])
    doc["chain_ok"] = ok
    if not ok:
        doc["status"] = "TAMPERED"
    return doc


def recompute_chain(doc: dict) -> str:
    """Re-derive a workflow run's chain_hash from its stored fields, exactly
    as run_workflow built it: header, then each step summary in order, then
    the final status. A stranger holding the receipt runs this and compares."""
    header = {"workflow": doc.get("workflow"), "endpoint": doc.get("endpoint"),
              "goal_excerpt": doc.get("goal_excerpt"),
              "started": doc.get("started")}
    chain = hashlib.sha256()
    chain.update(json.dumps(header, sort_keys=True, default=str).encode())
    for summary in doc.get("steps", []):
        chain.update(json.dumps(summary, sort_keys=True, default=str).encode())
    chain.update(json.dumps({"final_status": doc.get("status")},
                            sort_keys=True).encode())
    return chain.hexdigest()


def _step_summary(name: str, kind: str, status: str, result: dict | None,
                  note: str = "") -> dict:
    s = {"name": name, "kind": kind, "status": status}
    if note:
        s["note"] = note
    if result:
        final = str(result.get("final", ""))
        s["excerpt"] = final[:400]
        s["steps"] = result.get("steps")
        s["checkpoint"] = result.get("checkpoint")
        s["ledger_verified"] = result.get("verified")
        integrity = result.get("integrity")
        if isinstance(integrity, dict):
            s["integrity_clean"] = integrity.get("clean")
        if "tests_pass_trusted" in result:
            s["tests_pass_trusted"] = result["tests_pass_trusted"]
    return s


def _fixed_if_authorized(authorized: bool, exc: Exception) -> None:
    if not authorized:
        return
    if isinstance(exc, ProviderPermissionError):
        raise ProviderPermissionError() from None
    raise RuntimeError("authorized external action failed") from None


def _verify_step(step, endpoint, *, root, allow_write, test_cmd, proposer,
                 credential_bindings, authorized):
    try:
        result = run_router_agent(
            "Run the test command and report the outcome honestly.", endpoint,
            root=root, allow_exec=True, allow_write=allow_write, max_steps=2,
            test_cmd=test_cmd, proposer=proposer,
            credential_bindings=credential_bindings)
    except Exception as exc:
        _fixed_if_authorized(authorized, exc)
        return _step_summary(step["name"], "verify", "ERROR", None,
                             note=f"{type(exc).__name__}: {exc}"), "FAILED"
    trusted = bool(result.get("tests_pass_trusted"))
    status = "VERIFIED" if trusted else "FAILED"
    return _step_summary(step["name"], "verify", status, result), status


def _agent_step(step, goal, prev, endpoint, *, root, allow_write, allow_exec,
                allow_mcp, system, proposer, credential_bindings, authorized):
    step_goal = step["goal"].format(goal=goal, prev=prev)
    if system:
        step_goal = f"{system}\n\n{step_goal}"
    try:
        result = run_router_agent(
            step_goal, endpoint, root=root, allow_write=allow_write,
            allow_exec=allow_exec, allow_mcp=allow_mcp,
            max_steps=step.get("max_steps", 6), proposer=proposer,
            credential_bindings=credential_bindings)
    except Exception as exc:
        _fixed_if_authorized(authorized, exc)
        note = f"{type(exc).__name__}: {exc}"
        return _step_summary(step["name"], "agent", "ERROR", None,
                             note=note), prev, "FAILED", True
    summary = _step_summary(step["name"], "agent", "DONE", result)
    reasons = []
    if result.get("verified") is False:
        reasons.append("ledger did not verify")
    if summary.get("integrity_clean") is False:
        reasons.append("trajectory integrity dirty")
    if reasons:
        summary["status"] = "FAILED"
        summary["note"] = "; ".join(reasons)
        return summary, str(result.get("final", "")), "FAILED", True
    return summary, str(result.get("final", "")), None, False


def _persist_workflow(doc: dict, run_root, authorized: bool) -> None:
    if not run_root:
        return
    try:
        directory = Path(run_root) / "workflow_runs"
        directory.mkdir(parents=True, exist_ok=True)
        out = directory / f"{doc['chain_hash'][:16]}.json"
        out.write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
        doc["receipt_path"] = out.name
    except Exception as exc:
        _fixed_if_authorized(authorized, exc)
        doc["receipt_note"] = f"run not persisted: {type(exc).__name__}: {exc}"


def run_workflow(workflow: str, goal: str, endpoint: str, *, root: str = ".",
                 allow_write: bool = False, allow_exec: bool = False,
                 allow_mcp: bool = False, test_cmd: "str | None" = None,
                 system: str = "", run_root: "Path | str | None" = None,
                 proposer=None, credential_bindings=None,
                 authorized: bool = False) -> dict:
    """Run every step in order over `endpoint`. The gates passed here are the
    caller's actual grants; workflow definitions cannot widen them."""
    spec = WORKFLOWS.get(workflow)
    if spec is None:
        return {"schema": "flywheel.workflow-run/v1", "workflow": workflow,
                "status": "UNKNOWN_WORKFLOW",
                "known": sorted(WORKFLOWS)}
    started = time.strftime("%Y-%m-%dT%H:%M:%S")
    steps_out: list = []
    header = {"workflow": workflow, "endpoint": endpoint,
              "goal_excerpt": goal[:200], "started": started}
    chain = hashlib.sha256()
    chain.update(json.dumps(header, sort_keys=True, default=str).encode())
    prev = ""
    status = "COMPLETED"
    for step in spec["steps"]:
        if step["kind"] == "verify":
            if not (test_cmd and allow_exec):
                summary = _step_summary(step["name"], "verify", "UNVERIFIABLE",
                                        None, note="no test command granted; "
                                        "nothing was executed")
                status = "UNVERIFIED"
            else:
                summary, status = _verify_step(
                    step, endpoint, root=root, allow_write=allow_write,
                    test_cmd=test_cmd, proposer=proposer,
                    credential_bindings=credential_bindings,
                    authorized=authorized)
        else:
            summary, prev, changed, stop = _agent_step(
                step, goal, prev, endpoint, root=root,
                allow_write=allow_write, allow_exec=allow_exec,
                allow_mcp=allow_mcp, system=system, proposer=proposer,
                credential_bindings=credential_bindings,
                authorized=authorized)
            status = changed or status
        steps_out.append(summary)
        chain.update(json.dumps(summary, sort_keys=True, default=str).encode())
        if step["kind"] != "verify" and stop:
            break
    chain.update(json.dumps({"final_status": status}, sort_keys=True).encode())
    doc = {"schema": "flywheel.workflow-run/v1", "workflow": workflow,
           "endpoint": endpoint, "goal_excerpt": goal[:200], "started": started,
           "steps": steps_out, "status": status,
           "chain_hash": chain.hexdigest()}
    _persist_workflow(doc, run_root, authorized)
    return doc
