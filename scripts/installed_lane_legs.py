"""Run one acceptance leg against a started engine and collect check outcomes.

A leg reads the roster after the start probe settles, reads it twice more ten
seconds apart (the D1 guard: states must not move on their own), then runs the
leg's checks lane by lane through the granted routes the app uses. The setup
steps between the legs are here too, each the step the lane's card names.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from urllib.parse import quote

from scripts.installed_lane_cases import CASES, Check, Ctx
from scripts.installed_lane_client import Gateway, GrantedCalls
from scripts.installed_lane_engine import d1_unchanged, states_of, wait_settled
from scripts.installed_lane_verdict import (
    Outcome, evaluate_call, evaluate_home_path, evaluate_state, evaluate_tools)
from scripts.lane_smoke_fixtures import FIXTURES

_DETAIL_CHARS = 1500


def settle_and_guard(gw: Gateway, *, quiet_s: float = 15.0, gap_s: float = 10.0) -> dict:
    settled = wait_settled(gw.roster, quiet_s=quiet_s)
    rosters = [settled["roster"]]
    for _ in range(2):
        time.sleep(gap_s)
        rosters.append(gw.roster())
    return {"settled": settled["settled"], "settle_seconds": settled["seconds"],
            "d1_unchanged": d1_unchanged(rosters), "roster": rosters[-1],
            "by_state": rosters[-1].get("by_state"),
            "states": {k: {"state": v[0], "code": v[1]}
                       for k, v in sorted(states_of(rosters[-1]).items())}}


def _row(roster: dict, lane: str) -> dict | None:
    return next((r for r in roster.get("lanes", []) if r.get("name") == lane), None)


def _stub_generate(stub) -> int | None:
    return None if stub is None else stub.counts.snapshot().get("generate", 0)


def _run_call(check: Check, lane: str, calls: GrantedCalls, ctx: Ctx, stub,
              detail: dict) -> Outcome:
    steps = check.calls(ctx)
    for tool, args in steps[:-1]:
        status, body = calls.lane_call(lane, tool, args, tier=check.tier)
        if status != 200:
            detail[f"{lane}.{check.name}.{tool}"] = _clip(body)
            return Outcome("fail", {"status": status, "step": tool,
                                    "code": body.get("code") if isinstance(body, dict) else None})
    tool, args = steps[-1]
    before = _stub_generate(stub)
    status, body = calls.lane_call(lane, tool, args, tier=check.tier)
    after = _stub_generate(stub)
    delta = None if before is None or not check.stub_hit else after - before
    outcome = evaluate_call(check, status, body, stub_delta=delta)
    if isinstance(body, dict):
        extra = {k: body[k] for k in ("reason", "stage") if isinstance(body.get(k), str)}
        outcome = Outcome(outcome.result, {**outcome.evidence, **extra})
    if outcome.result != "pass" or status != 200:
        detail[f"{lane}.{check.name}"] = _clip(body)
    return outcome


def _clip(body: object) -> str:
    return json.dumps(body, sort_keys=True, default=str)[:_DETAIL_CHARS]


def run_leg(leg: str, gw: Gateway, calls: GrantedCalls, roster: dict, *, ctx: Ctx,
            host: dict, stub=None) -> tuple[dict, dict]:
    """Every check of ``leg`` for every lane: {lane: {check: Outcome}}, detail."""
    outcomes: dict = {}
    detail: dict = {}
    for lane, case in CASES.items():
        got = outcomes.setdefault(lane, {})
        for check in (c for c in case.checks if c.leg == leg):
            got[check.name] = _one(check, lane, calls, roster, ctx, host, stub, detail)
    return outcomes, detail


def _one(check: Check, lane: str, calls: GrantedCalls, roster: dict, ctx: Ctx,
         host: dict, stub, detail: dict) -> Outcome:
    if check.kind == "state":
        return evaluate_state(check, _row(roster, lane), host=host)
    if check.kind == "tools":
        status, body = calls.list_tools(lane)
        outcome = evaluate_tools(lane, status, body)
        if outcome.result != "pass":
            detail[f"{lane}.{check.name}"] = _clip(body)
        return outcome
    if check.kind == "home_path":
        return evaluate_home_path(check, ctx.home)
    return _run_call(check, lane, calls, ctx, stub, detail)


def place_canon_block(ctx: Ctx) -> Path:
    """The canon card's step: put a block in <home>/lanes/canon/blocks."""
    FIXTURES["canon"].calls(ctx.home, ctx.lane_work("canon"))
    return ctx.home / "lanes" / "canon" / "blocks"


def make_fixture_repo(ctx: Ctx, git: str | None) -> dict:
    """A one-commit git repository for index.map, made with the host's Git."""
    repo = ctx.lane_work("index") / "git-repo"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "mod_a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    if not git:
        return {"git_repo": False, "reason": "no_git_given"}
    ident = ["-c", "user.name=wp11", "-c", "user.email=wp11@example.invalid"]
    for argv in (["init", "-q"], ["add", "mod_a.py"], [*ident, "commit", "-qm", "fixture"]):
        done = subprocess.run([git, "-C", str(repo), *argv], capture_output=True, check=False)
        if done.returncode != 0:
            return {"git_repo": False, "reason": "git_" + argv[0]}
    return {"git_repo": True}


def make_project_folder(ctx: Ctx) -> Path:
    ctx.project.mkdir(parents=True, exist_ok=True)
    (ctx.project / "README.md").write_text("# WP11 project\n\nA picked folder.\n",
                                           encoding="utf-8")
    return ctx.project


def record_writing_draft(gw: Gateway, token: str, ctx: Ctx) -> dict:
    """The writing card's step: record a draft through the Writing routes."""
    from scripts.frozen_gateway_native_smoke import run_writing_acceptance_smoke
    try:
        done = run_writing_acceptance_smoke(gw.base, token, secrets=(token,))
    except (RuntimeError, ValueError, OSError) as err:
        return {"ok": False, "error": type(err).__name__, "code": str(err)[:80]}
    journey = done["journey_ref"]
    status, view = gw.request("GET", f"/api/writing/project?journey_ref={quote(journey)}")
    sections = view.get("sections") if isinstance(view, dict) else None
    revision = sections[0].get("current_revision_ref") if sections else None
    ctx.writing.update({"journey_ref": journey, "event_head": done["event_head_sha256"],
                        "project_ref": view.get("project_ref") if isinstance(view, dict)
                        else None, "revision_ref": revision})
    if not ctx.writing["project_ref"]:
        ctx.writing["project_ref"] = "wpr_" + "a" * 32   # the fixture's project ref
    return {"ok": status == 200 and bool(revision), "routes": len(done["routes"])}
