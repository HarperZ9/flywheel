"""A Claude Code session a lane started is not imported as the owner's.

Security review of 1.1.0, finding 6: every lane child runs with capture off,
which stops the hooks only. articulate runs ``claude -p`` from a private
folder under its lane folder, Claude Code keeps that session under
``~/.claude/projects``, and ``flywheel traces import --client claude-code``
walked every project folder, so it would have imported the owner's document
text and articulate's system prompt as the owner's own transcripts. The
importer now reads the working directory the transcript records (never the
lossy folder slug) and skips a session that ran under ``<home>/lanes/``,
naming it LANE_SPAWNED in the plan.
"""
from __future__ import annotations

import json

import pytest

from harness.trace_import_claude import plan_claude
from import_fixtures import OWNER, SESSION, age_tree
from trace_enc_fakes import StreamTestProvider, using

LANE_SESSION = "9c2e4d61-0a7b-4f3e-8d15-2b6a9e0c4f37"


def _transcript(session, cwd) -> bytes:
    records = ({"type": "summary", "summary": "no cwd on this line"},
               {"type": "user", "sessionId": session, "cwd": cwd,
                "message": {"role": "user", "content": "rewrite this paragraph"}})
    return b"".join(json.dumps(r).encode() + b"\n" for r in records)


@pytest.fixture
def world(tmp_path):
    home = tmp_path / "home"
    (home / "state").mkdir(parents=True)
    (home / "owner.ref").write_text(OWNER)
    root = tmp_path / "claude"
    lane_cwd = home / "lanes" / "articulate" / "tmp" / "articulate-x" / "cwd"
    lane_cwd.mkdir(parents=True)
    lane_project = root / "projects" / "C--lane-slug-is-lossy"
    (lane_project / LANE_SESSION / "tool-results").mkdir(parents=True)
    (lane_project / f"{LANE_SESSION}.jsonl").write_bytes(_transcript(LANE_SESSION,
                                                                     str(lane_cwd)))
    (lane_project / LANE_SESSION / "tool-results" / "r.txt").write_bytes(b"lane output")
    owner_project = root / "projects" / "C--work-demo"
    owner_project.mkdir(parents=True)
    (owner_project / f"{SESSION}.jsonl").write_bytes(_transcript(SESSION,
                                                                 str(tmp_path / "work")))
    age_tree(root, seconds=300)
    with using(StreamTestProvider()):
        yield home, root


def test_a_lane_spawned_session_is_skipped_and_named(world):
    home, root = world
    plan = plan_claude(home, root=root)
    sessions = {item["session_id"] for item in plan["items"]}
    assert sessions == {SESSION}
    assert plan["lane_spawned"] == 1
    skipped = [row for row in plan["not_imported"] if row["reason"] == "LANE_SPAWNED"]
    assert [row["name"] for row in skipped] == [
        f"projects/C--lane-slug-is-lossy/{LANE_SESSION}.jsonl",
        f"projects/C--lane-slug-is-lossy/{LANE_SESSION}/tool-results/r.txt"]


def test_control_without_a_lane_folder_every_session_is_planned(world, tmp_path):
    home, root = world
    other_home = tmp_path / "other-home"
    (other_home / "state").mkdir(parents=True)
    (other_home / "owner.ref").write_text(OWNER)
    plan = plan_claude(other_home, root=root)
    assert {item["session_id"] for item in plan["items"]} == {SESSION, LANE_SESSION}
    assert plan["lane_spawned"] == 0
