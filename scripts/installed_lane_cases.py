"""What the installed-app acceptance checks per lane (PLAN.md section 1b, WP11).

Each lane has a list of checks in two legs. ``fresh`` is a new install with no
setup (``FLYWHEEL_GIT=none``, no project folder, no canon block, no draft, no
stub model server). ``setup`` is the same home after the harness did each
stated setup step the app names: Git pointed at, the stub model server at
127.0.0.1:8765, the local-model folder chosen through its granted route, a
canon block placed, and a writing draft recorded through the Writing routes.

A lane is in its class only when every check passes. ``class_plan`` is the
section 1a target; ``class_expected`` is the target after the operator
decisions recorded in DECISIONS.json and POLICY-DECISION.md, with the basis.
Main-tool fixtures come from ``lane_smoke_fixtures`` (test fixtures, not
shipped content).
"""
from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from scripts.lane_smoke_fixtures import FIXTURES
from scripts.stub_model_server import REPLY_TEXT as STUB_REPLY

REFUSED = -1          # a non-200 answer; a refusal check must name ``expect_code``
DENIED = 403          # the governance gate's tier refusal: 403 with governance_denied
Call = tuple[str, dict]


@dataclass
class Ctx:
    """What a check's arguments are built from, filled as the run goes."""
    home: Path
    work: Path
    project: Path
    writing: dict = field(default_factory=dict)

    def lane_work(self, lane: str) -> Path:
        path = self.work / lane
        path.mkdir(parents=True, exist_ok=True)
        return path


@dataclass(frozen=True)
class Check:
    name: str
    leg: str                                   # "fresh" | "setup"
    kind: str                                  # "state" | "tools" | "call" | "home_path"
    states: tuple[str, ...] = ()
    code: str = ""                             # state code, when it matters
    tool: str = ""
    calls: Callable[[Ctx], list[Call]] | None = None
    tier: str = "T1"
    expect_status: int = 200
    expect_code: str = ""
    assert_: Callable[[object], bool] | None = None
    confound: str = ""                         # host fact that can hide this state
    stub_hit: bool = False                     # the call must reach the stub model server
    path: tuple[str, ...] = ()                 # home_path: a folder under the home


@dataclass(frozen=True)
class LaneCase:
    lane: str
    class_plan: str
    class_expected: str
    basis: str
    checks: tuple[Check, ...]
    untested: tuple[str, ...] = ()


RUNS = ("ready", "limited")


def st(leg: str, *states: str, code: str = "", confound: str = "") -> Check:
    return Check(f"{leg}_state", leg, "state", states=states, code=code, confound=confound)


def tools(leg: str) -> Check:
    return Check(f"{leg}_tools", leg, "tools")


def fx(leg: str, lane: str, *, stub_hit: bool = False) -> Check:
    fixture = FIXTURES[lane]
    calls = lambda ctx: fixture.calls(ctx.home, ctx.lane_work(lane))  # noqa: E731
    return Check(f"{leg}_main", leg, "call", tool=_last_tool(lane), calls=calls,
                 assert_=fixture.check, stub_hit=stub_hit)


def call(name: str, leg: str, tool: str, args: Callable[[Ctx], dict], *,
         status: int = 200, code: str = "", assert_=None, tier: str = "T1",
         stub_hit: bool = False) -> Check:
    return Check(name, leg, "call", tool=tool, calls=lambda ctx: [(tool, args(ctx))],
                 tier=tier, expect_status=status, expect_code=code, assert_=assert_,
                 stub_hit=stub_hit)


def _last_tool(lane: str) -> str:
    with tempfile.TemporaryDirectory(prefix="wp11-tool-") as scratch:
        return FIXTURES[lane].calls(Path(scratch) / "home", Path(scratch) / "work")[-1][0]


def find_key(value: object, key: str) -> object:
    """The first value stored under ``key`` anywhere in a JSON value."""
    if isinstance(value, dict):
        if key in value:
            return value[key]
        value = list(value.values())
    if isinstance(value, list):
        for item in value:
            found = find_key(item, key)
            if found is not None:
                return found
    return None


def _repo(ctx: Ctx) -> dict:
    # A git repository the harness made with the host's Git before the run
    # (installed_lane_legs.make_fixture_repo), so index.map has history to read.
    return {"root": str(ctx.lane_work("index") / "git-repo")}


def _map_ok(reply: object) -> bool:
    count = find_key(reply, "repo_count")
    return find_key(reply, "metadata_status") == "ok" and isinstance(count, int) and count >= 1


def _local_run_ok(reply: object) -> bool:
    # harness.local_loop's result: the model's final text and a verified ledger.
    return (isinstance(reply, dict) and reply.get("final") == STUB_REPLY
            and reply.get("verified") is True
            and "WORKSPACE_PROTECTED" not in json.dumps(reply))


def _workflow_unjoinable(reply: object) -> bool:
    # The installed app has no gather, crucible, index or forum source folder
    # beside the staged package, so an approved workflow call answers with the
    # lane's own UNVERIFIABLE envelope and starts none of their programs.
    return (isinstance(reply, dict) and reply.get("status") == "UNVERIFIABLE"
            and find_key(reply, "reason") == "flagship_workflow_unjoinable")


def _build_proof_match(reply: object) -> bool:
    # telos.proof.build recomputes the bundled demo run's invariant in memory;
    # the verifier's own verdict must be MATCH with no failed check.
    verifier = reply.get("verifier") if isinstance(reply, dict) else None
    return (isinstance(verifier, dict)
            and reply.get("schema") == "project-telos.build-proof-packet/v1"
            and verifier.get("verdict") == "MATCH" and verifier.get("failures") == [])


# A caller's arguments to a telos tool: the engine passes none of them on.
_STRAY = {"stray": "x", "--out": "stray.json"}


def _diagnose_args(ctx: Ctx) -> dict:
    w = ctx.writing
    return {"journey_ref": w.get("journey_ref"), "expected_event_head": w.get("event_head"),
            "project_ref": w.get("project_ref"), "revision_ref": w.get("revision_ref"),
            "client_request_id": "wp11-writing-diagnose"}


_GOAL = {"goal": "Reply with the word ok.", "max_steps": 1}


def _read_lane(lane: str, plan: str = "A", basis: str = "PLAN 1a", extra=()) -> LaneCase:
    return LaneCase(lane, plan, plan, basis,
                    (st("fresh", *RUNS), tools("fresh"), fx("fresh", lane), *extra))


CASES: dict[str, LaneCase] = {c.lane: c for c in (
    _read_lane("gather", basis="PLAN 1a; feeds need network and are not run"),
    _read_lane("crucible"),
    _read_lane("chorus"),
    _read_lane("articulate", basis="PLAN 1a; judge, fix and polish are T2 behind a "
               "signed-in claude CLI (O-14, articulate 0.5.0)", extra=(
        call("fresh_judge_t1_refused", "fresh", "judge", lambda c: {"text": "x"},
             status=DENIED),)),
    LaneCase("index", "A/B", "A/B", "PLAN 1a: symbols A, map B (Git)", (
        st("fresh", "limited"), tools("fresh"), fx("fresh", "index"),
        call("fresh_map_needs_git", "fresh", "index.map", _repo, status=REFUSED,
             code="LANE_SETUP_REQUIRED"),
        st("setup", "ready"),
        call("setup_map", "setup", "index.map", _repo, assert_=_map_ok))),
    LaneCase("forum", "A/B-untested", "A/B-untested", "PLAN 1a", (
        st("fresh", *RUNS), tools("fresh"), fx("fresh", "forum")),
        untested=("real rooms need FORUM_RUN_REAL and a provider key",)),
    _read_lane("learn", basis="PLAN 1a said B (Node); O-1 b bundles Node, so A"),
    _read_lane("telos", basis="PLAN 1a said B (Node); telos 0.4.2 runs on the bundled "
               "Node, so A. room, workflow and proof start programs outside the package "
               "and run only at T2; native.control stays out of the build; the engine "
               "passes telos no argument", extra=(
        call("fresh_catalog_drops_arguments", "fresh", "telos.catalog",
             lambda c: dict(_STRAY), assert_=FIXTURES["telos"].check),
        call("fresh_proof_build", "fresh", "telos.proof.build", lambda c: {},
             assert_=_build_proof_match),
        call("fresh_room_t1_refused", "fresh", "telos.room", lambda c: {}, status=DENIED),
        call("fresh_proof_t1_refused", "fresh", "telos.proof", lambda c: {}, status=DENIED),
        call("fresh_workflow_t1_refused", "fresh", "telos.workflow", lambda c: {},
             status=DENIED),
        call("fresh_workflow_t2_runs", "fresh", "telos.workflow", lambda c: {}, tier="T2",
             assert_=_workflow_unjoinable),
        call("fresh_native_control_not_in_build", "fresh", "telos.native.control",
             lambda c: {}, tier="T2", status=REFUSED, code="NOT_IN_BUILD"))),
    LaneCase("local-model", "B", "B", "PLAN 1a: model server and project folder", (
        st("fresh", "needs_setup"),
        call("fresh_run_needs_setup", "fresh", "local_agent_run",
             lambda c: dict(_GOAL), status=REFUSED, code="LANE_SETUP_REQUIRED"),
        st("setup", *RUNS), tools("setup"),
        call("setup_main", "setup", "local_agent_run",
             lambda c: {**_GOAL, "root": str(c.project)}, assert_=_local_run_ok,
             stub_hit=True))),
    LaneCase("writing", "A", "B", "POLICY-DECISION C-5: diagnose is T2 behind a "
             "recorded draft", (
        st("fresh", "needs_setup"), tools("fresh"), st("setup", *RUNS),
        call("setup_main", "setup", "writing.diagnose", _diagnose_args, tier="T2",
             assert_=lambda r: isinstance(find_key(r, "proposal_ref"), str)))),
    LaneCase("relay", "B", "B", "PLAN 1a: model server; relay 0.5.0 pinned", (
        st("fresh", "needs_setup", confound="model_server"), tools("fresh"),
        st("setup", *RUNS), fx("setup", "relay", stub_hit=True),
        call("setup_start_t1_refused", "setup", "local_agent_start",
             lambda c: dict(_GOAL), status=DENIED))),
    _read_lane("plexus"),
    _read_lane("mneme", extra=(
        Check("fresh_state_in_lane_folder", "fresh", "home_path",
              path=("lanes", "mneme")),)),
    LaneCase("calibrate-pro", "C", "C", "PLAN 1a; O-2 default catalog slice", (
        st("fresh", "reads_only"), tools("fresh"), fx("fresh", "calibrate-pro"),
        call("fresh_list_targets_not_in_build", "fresh", "calibrate-pro.list-targets",
             lambda c: {}, status=REFUSED, code="NOT_IN_BUILD"))),
    LaneCase("canon", "B", "B", "PLAN 1a: the person places blocks", (
        st("fresh", "needs_setup"), tools("fresh"), st("setup", *RUNS),
        fx("setup", "canon"))),
    # The build selects no Bulletin deployment, so a fresh install must name the
    # endpoint variable and refuse a board read without sending any request.
    LaneCase("bulletin", "A", "B", "PLAN 1a; no deployment in the build: the person "
             "sets FLYWHEEL_BULLETIN_URL (zero publisher compute)", (
        st("fresh", "needs_setup"),
        call("fresh_main_needs_endpoint", "fresh", "board_rooms", lambda c: {},
             status=REFUSED, code="LANE_SETUP_REQUIRED")),
        untested=("board reads need an operator-selected endpoint",
                  "board writes need a registered identity")),
    LaneCase("accountable-surface", "A/C", "A/C", "PLAN 1a; actuation out of the build "
             "(O-13 default)", (
        st("fresh", *RUNS), tools("fresh"), fx("fresh", "accountable-surface"),
        call("fresh_actuate_refused", "fresh", "accountable-surface.actuate",
             lambda c: {}, status=DENIED))),
    LaneCase("isomorph", "B", "held", "private lane; source checkout only", (
        st("fresh", "cannot_launch", code="lane_held"),)),
    LaneCase("sofer", "B", "held", "private lane; source checkout only", (
        st("fresh", "cannot_launch", code="lane_held"),)),
    LaneCase("array", "B", "held", "private lane; source checkout only", (
        st("fresh", "cannot_launch", code="lane_held"),)),
)}
