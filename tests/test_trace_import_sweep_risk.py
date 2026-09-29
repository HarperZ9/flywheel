"""A11: Claude Code deletes transcripts after cleanupPeriodDays (30 by default).
The plan names every transcript within seven days of that sweep that is not
imported yet, so silent loss becomes a visible list."""
import json

import pytest

from harness.trace_import_claude import plan_claude
from harness.trace_import_core import run_import
from import_fixtures import OWNER, PROJECT, SESSION, claude_tree, old
from trace_enc_fakes import StreamTestProvider, using


@pytest.fixture
def tree(tmp_path):
    home = tmp_path / "home"
    (home / "state").mkdir(parents=True)
    (home / "owner.ref").write_text(OWNER)
    root, _, _ = claude_tree(tmp_path)
    with using(StreamTestProvider()):
        yield home, root


def test_a_transcript_near_the_sweep_is_at_risk_until_imported(tree):
    home, root = tree
    old(root / "projects" / PROJECT / f"{SESSION}.jsonl", days=25)
    plan = plan_claude(home, root=root)
    assert plan["sweep"] == {"cleanup_period_days": 30, "source": "user settings",
                             "at_risk": 1}
    run_import(home, plan)
    assert plan_claude(home, root=root)["sweep"]["at_risk"] == 0


def test_a_recent_transcript_is_not_at_risk(tree):
    home, root = tree
    assert plan_claude(home, root=root)["sweep"]["at_risk"] == 0


def test_a_longer_period_in_settings_moves_the_window(tree):
    home, root = tree
    (root / "settings.json").write_text(json.dumps({"cleanupPeriodDays": 3650}))
    old(root / "projects" / PROJECT / f"{SESSION}.jsonl", days=25)
    assert plan_claude(home, root=root)["sweep"]["at_risk"] == 0


def test_a_recently_written_file_is_a_live_writer_and_retried_later(tree):
    home, root = tree
    plan = plan_claude(home, root=root, live_window_s=3600)
    assert {i["state"] for i in plan["items"]} == {"LIVE_WRITER"}
    assert run_import(home, plan)["skipped"]["LIVE_WRITER"] == 5
