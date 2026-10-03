"""The lane path guard and the local-model folder rule protect the run root too.

Security review of the 1.1.0 change, finding 5. The run root holds agent runs,
snapshots, lessons, eval and workflow runs, which can carry the same content as
a trace. It sits under the Flywheel home only by default: FLYWHEEL_RUN_ROOT, a
``.flywheel-run-root`` marker or a non-default FLYWHEEL_HOME each put it
elsewhere, and a guard that protected the home alone let a T1 path argument or
a local-model project folder reach it.
"""
from __future__ import annotations

import pytest

from harness.lane_tier_gate import argument_refusal
from harness.local_agent_grants import GrantRefusal, grants_from_config


@pytest.fixture()
def roots(tmp_path, monkeypatch):
    home = tmp_path / "home"
    run = tmp_path / "elsewhere" / "run"
    for folder in (home / "lanes" / "gather", run / "agent_runs"):
        folder.mkdir(parents=True)
    (run / "agent_runs" / "r1.json").write_text("{}", encoding="utf-8")
    (tmp_path / "work").mkdir()
    (tmp_path / "work" / "notes.md").write_text("x", encoding="utf-8")
    monkeypatch.setenv("FLYWHEEL_HOME", str(home))
    monkeypatch.setenv("FLYWHEEL_RUN_ROOT", str(run))
    return tmp_path, home, run


def _refused(value) -> bool:
    refusal = argument_refusal("gather", "gather.docs", {"path": str(value)})
    return bool(refusal) and refusal["reason"] == "argument_refused"


def test_a_lane_path_argument_under_the_run_root_is_refused(roots):
    tmp, _home, run = roots
    assert _refused(run / "agent_runs" / "r1.json")
    assert _refused(run)
    assert not _refused(tmp / "work" / "notes.md")          # control: an ordinary file


@pytest.mark.parametrize("pick", ["run", "holder", "inside"])
def test_a_local_model_folder_at_inside_or_holding_the_run_root_is_refused(roots, pick):
    tmp, _home, run = roots
    folder = {"run": run, "holder": tmp / "elsewhere", "inside": run / "agent_runs"}[pick]
    with pytest.raises(GrantRefusal) as refused:
        grants_from_config({"FLYWHEEL_HOME": str(_home), "FLYWHEEL_RUN_ROOT": str(run)},
                           workspace=str(folder))
    assert refused.value.code == "WORKSPACE_PROTECTED"


def test_an_ordinary_project_folder_is_still_accepted(roots):
    tmp, home, run = roots
    grants = grants_from_config({"FLYWHEEL_HOME": str(home), "FLYWHEEL_RUN_ROOT": str(run)},
                                workspace=str(tmp / "work"))
    assert grants.workspace.endswith("work")


def test_the_state_roots_are_the_home_and_the_run_root(roots):
    from harness.flywheel_state_roots import state_roots
    _tmp, home, run = roots
    found = state_roots({"FLYWHEEL_HOME": str(home), "FLYWHEEL_RUN_ROOT": str(run)})
    assert [p.lower() for p in found] == [str(home.resolve()).lower(), str(run.resolve()).lower()]
