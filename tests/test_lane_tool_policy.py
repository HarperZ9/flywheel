"""The lane tool policy table: coverage, the T2 rule and the reviewed draft.

The table is ``harness/lane_tool_policy.py``. These tests hold it to three
sources that do not come from the table itself:

- the tools each lane serves (the payload rows' ``static_tool_names``, the Node
  lane pins, the engine's own local-model and writing modules, and the bulletin
  0.5.0 tool list read from its source at tag v0.5.0);
- the T2 rule: a tool that writes outside the lane's own folder, spends a model
  call or provider key, publishes, actuates or decides a human approval is T2;
- the plan's section 1a draft, written out here by hand, so an edit to the table
  that quietly opens a T2 tool fails a test that the table cannot rewrite.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness import lane_tool_policy as policy
from harness.lanes_registry import LANES

ROOT = Path(__file__).resolve().parents[1]

# bulletin 0.5.0 (tag v0.5.0, ba75ef52): src/tools/health.ts, read.ts, write.ts.
BULLETIN_050_TOOLS = (
    "bulletin_status", "bulletin_doctor",
    "board_rooms", "board_feed", "board_search", "board_thread", "board_post",
    "board_agents", "board_agent", "board_digest", "board_reports", "board_bounties",
    "board_bounty", "board_stats", "board_moderation_log",
    "board_write_post", "board_upload_media", "board_flag_post", "board_create_room",
    "board_create_bounty", "board_revise_bounty_terms", "board_claim_bounty",
    "board_release_bounty_claim", "board_submit_bounty_evidence",
    "board_review_bounty_submission", "board_inbox", "board_ack_receipt", "board_whoami",
    "board_update_profile", "board_promote", "board_rotate_key",
)

# Section 1a names these T2, or they change something the T2 rule covers.
MUST_BE_T2 = {
    "gather": ("gather.run", "gather.pilot", "gather.federation"),
    "crucible": ("crucible.run", "crucible.batch", "crucible.refine"),
    "index": ("index.invalidate",),
    "forum": ("submit", "forum.submit", "forum.run.room", "forum.prose.humanize",
              "gate_approve", "gate_edit", "gate_reject"),
    "learn": ("learn_tutor_record",),
    "mneme": ("mneme.forget", "mneme.to_crucible", "mneme.replay_crucible"),
    "canon": ("canon.render",),
    "writing": ("writing.project_init", "writing.section_record", "writing.revision_record",
                "writing.card_record", "writing.candidate_record", "writing.decision_record",
                "writing.review_prepare", "writing.export_prepare", "writing.proposal_commit"),
    "accountable-surface": ("accountable-surface.propose", "accountable-surface.actuate"),
    "bulletin": ("board_write_post", "board_upload_media", "board_flag_post",
                 "board_create_room", "board_create_bounty", "board_revise_bounty_terms",
                 "board_claim_bounty", "board_release_bounty_claim",
                 "board_submit_bounty_evidence", "board_review_bounty_submission",
                 "board_ack_receipt", "board_update_profile", "board_promote",
                 "board_rotate_key"),
    "articulate": ("judge", "fix", "polish"),
    "local-model": ("flywheel.context.capture",),
}

# Section 1a: the lane's main action, as T1 tools.
MAIN = {
    "gather": {"gather.docs", "gather.context"},
    "crucible": {"crucible.assess"},
    "chorus": {"chorus.run"},
    "articulate": {"score", "check"},
    "index": {"index.map", "index.symbol-definition", "index.symbol-references"},
    "forum": {"forum.route", "plan"},
    "learn": {"learn_dry_run", "learn_tutor_plan"},
    "telos": {"telos.catalog", "telos.doctor"},
    "local-model": {"local_agent_run", "local_agent_chat"},
    "writing": {"writing.diagnose"},
    "relay": {"local_agent_run"},
    "plexus": {"plexus_route", "plexus_plan"},
    "mneme": {"mneme.remember", "mneme.recall"},
    "calibrate-pro": {"calibrate-pro.list-panels", "calibrate-pro.panel-info"},
    "canon": {"canon.validate", "canon.check"},
    "bulletin": {"board_rooms", "board_feed"},
    "accountable-surface": {"accountable-surface.perceive"},
}

NOT_IN_BUILD = {
    "articulate": {"judge", "fix", "polish"},
    "index": {"index.router.job.start", "index.router.job.status", "index.router.job.result",
              "index.router.job.cancel", "index.router.job.resume"},
    "relay": {"local_agent_start", "local_agent_status", "local_agent_result"},
    "calibrate-pro": {"calibrate-pro.list-targets"},
    "telos": {"telos.native.control", "telos.room", "telos.workflow"},
    "writing": {"writing.proposal_approve"},
}


def _served_tools() -> dict[str, tuple[str, ...]]:
    served: dict[str, tuple[str, ...]] = {}
    for line in (ROOT / "packaging" / "python-lane-payloads.jsonl").read_text(
            encoding="utf-8").splitlines():
        row = json.loads(line)
        served[row["lane"]] = tuple(row["mcp"]["static_tool_names"])
    node = json.loads((ROOT / "packaging" / "node-lane-payloads.json").read_text(
        encoding="utf-8"))
    for row in node["lanes"]:
        served[row["lane"]] = tuple(row["static_tool_names"])
    from harness import local_mcp, writing_mcp
    served["local-model"] = tuple(t["name"] for t in local_mcp.TOOLS)
    served["writing"] = tuple(t["name"] for t in writing_mcp.TOOLS)
    served["bulletin"] = BULLETIN_050_TOOLS
    return served


def test_the_table_is_sound():
    assert policy.validate_policy() == []


def test_every_registry_lane_has_a_table():
    assert set(policy.LANE_TOOL_POLICY) == set(LANES)


@pytest.mark.parametrize("lane", sorted(LANES))
def test_the_table_lists_exactly_the_tools_the_lane_serves(lane):
    served = _served_tools()[lane]
    listed = tuple(policy.lane_policy(lane))
    assert sorted(listed) == sorted(served), (
        f"{lane}: listed but not served {sorted(set(listed) - set(served))}; "
        f"served but not listed {sorted(set(served) - set(listed))}")


@pytest.mark.parametrize("lane", sorted(LANES))
def test_admitted_tools_are_served_t1_and_in_the_build(lane):
    table = policy.lane_policy(lane)
    for name in policy.admitted_tools(lane):
        assert name in _served_tools()[lane]
        assert table[name].tier == "T1"
        assert not table[name].not_in_build


def test_every_tool_the_t2_rule_covers_is_t2():
    for lane, tools in policy.LANE_TOOL_POLICY.items():
        for name, entry in tools.items():
            if entry.effect in policy.T2_EFFECTS:
                assert entry.tier == "T2", f"{lane} {name}: {entry.effect} at {entry.tier}"


@pytest.mark.parametrize("lane,tool", [(lane, tool) for lane, tools in MUST_BE_T2.items()
                                       for tool in tools])
def test_the_reviewed_t2_tools_stay_t2(lane, tool):
    assert policy.lane_policy(lane)[tool].tier == "T2"
    assert tool not in policy.admitted_tools(lane)


def test_every_lane_has_a_main_tool_or_is_reads_only():
    for lane in LANES:
        assert policy.main_tools(lane) or lane in policy.READS_ONLY_LANES, lane


@pytest.mark.parametrize("lane", sorted(MAIN))
def test_main_tools_follow_section_1a(lane):
    assert set(policy.main_tools(lane)) == MAIN[lane]
    for name in policy.main_tools(lane):
        assert name in policy.admitted_tools(lane), f"{lane} {name} is main but not admitted"


def test_calibrate_pro_is_the_reads_only_lane():
    assert policy.READS_ONLY_LANES == {"calibrate-pro": policy.READS_ONLY_LANES["calibrate-pro"]}
    assert policy.READS_ONLY_LANES["calibrate-pro"]


@pytest.mark.parametrize("lane", sorted(NOT_IN_BUILD))
def test_not_in_build_follows_section_1a(lane):
    marked = {name for name, entry in policy.lane_policy(lane).items() if entry.not_in_build}
    assert marked == NOT_IN_BUILD[lane]


@pytest.mark.parametrize("lane", ["relay", "local-model"])
def test_an_agent_run_on_the_app_route_never_gets_write_or_exec(lane):
    forced = dict(policy.lane_policy(lane)["local_agent_run"].forced_args)
    assert forced == {"allow_write": False, "allow_exec": False}


def test_argument_guards_drop_every_write_path_on_t1_tools():
    assert dict(policy.lane_policy("index")["index.map"].forced_args) == {"resume_state": None}
    assert dict(policy.lane_policy("crucible")["crucible.report"].forced_args) == {"out": None}
    assert dict(policy.lane_policy("crucible")["crucible.registry"].forced_args) == {
        "apply": False}


def test_guard_args_forces_and_drops_without_touching_the_caller_dict():
    args = {"goal": "g", "allow_write": True, "allow_exec": True}
    guarded = policy.guard_args("relay", "local_agent_run", args)
    assert guarded == {"goal": "g", "allow_write": False, "allow_exec": False}
    assert args["allow_exec"] is True
    assert policy.guard_args("index", "index.map", {"root": "r", "resume_state": "x"}) == {
        "root": "r"}
    assert policy.guard_args("gather", "gather.docs", {"path": "p"}) == {"path": "p"}


def test_needs_name_only_known_setup_items():
    for lane, tools in policy.LANE_TOOL_POLICY.items():
        for name, entry in tools.items():
            assert set(entry.needs) <= set(policy.SETUP_ITEMS), f"{lane} {name}"


def test_a_schema_break_is_reported():
    bad = {"x": {"x.a": policy.ToolPolicy(tier="T1", effect="publish", reason="r"),
                 "x.b": policy.ToolPolicy(effect="teleport", reason="r"),
                 "x.c": policy.ToolPolicy(needs=("moon",), reason="r"),
                 "x.d": policy.ToolPolicy()}}
    problems = "\n".join(policy.validate_policy(bad))
    assert "x.a: effect 'publish' needs T2" in problems
    assert "x.b: effect 'teleport'" in problems
    assert "x.c: unknown setup item 'moon'" in problems
    assert "x.d: no reason" in problems


def test_the_review_document_carries_the_rendered_tables():
    """The tables in the review cannot drift from the table of record."""
    from scripts.render_lane_policy_review import render_tables
    doc = (ROOT / "project-docs" / "lanes" / "POLICY-REVIEW.md").read_text(encoding="utf-8")
    assert render_tables() in doc
