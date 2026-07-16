"""The schema-trace intake must be zero-trust like the forum intake beside
it: a trajectory is admitted only after THIS code re-derives its grade from
the raw events under the published RHAE definition, the events file is
content-addressed at import so a later edit reads as DRIFT, and a malformed
log (non-contiguous steps, WIN with unassigned actions) is refused loudly,
never silently admitted."""

import json

import pytest

from harness.schema_trace_intake import (SchemaTraceError, load_trajectory,
                                         recheck, rhae, stream_summary,
                                         to_gradable_row)


def _write_events(path, per_level, state="WIN", contiguous=True,
                  trailing_actions=0):
    """A tiny synthetic events.jsonl: `per_level` action counts, each level
    closed by level_up on its last action."""
    lines = [{"kind": "run_started", "seq": 1, "ts": 1.0,
              "game_id": "zz99-test", "resumed_transitions": 0}]
    step = 0
    for count in per_level:
        for i in range(count):
            step_index = step if contiguous else step + (7 if step > 0 else 0)
            lines.append({"kind": "action_taken", "seq": len(lines) + 1,
                          "ts": 1.0, "step_index": step_index,
                          "state": "NOT_FINISHED",
                          "level_up": i == count - 1})
            step += 1
    for _ in range(trailing_actions):
        lines.append({"kind": "action_taken", "seq": len(lines) + 1,
                      "ts": 1.0, "step_index": step,
                      "state": "NOT_FINISHED", "level_up": False})
        step += 1
    lines.append({"kind": "run_finished", "seq": len(lines) + 1, "ts": 2.0,
                  "state": state, "actions": step})
    path.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")


def _trajectory_dir(tmp_path, per_level, state="WIN", **kw):
    d = tmp_path / "claude-fable-5_max_zz99_0.0"
    d.mkdir()
    _write_events(d / "events.jsonl", per_level, state=state, **kw)
    (d / "run.json").write_text(json.dumps(
        {"game_id": "zz99-test", "provider": "claude",
         "model": "claude-fable-5", "max_actions": 3000,
         "started_at": 1.0}), encoding="utf-8")
    return d


def test_rhae_matches_the_published_definition():
    # equal to baseline -> 100 per level, 100 game
    per_level, game = rhae([10, 20], [10, 20])
    assert per_level == [100.0, 100.0] and game == 100.0
    # better than baseline is capped at 115 per level
    per_level, _ = rhae([10], [5])
    assert per_level == [115.0]
    # a stopped run earns only the completed-weight share
    per_level, game = rhae([10, 20], [10])
    assert per_level == [100.0, 0.0]
    assert game == pytest.approx(100.0 / 3)  # completion cap 1/(1+2)


def test_summary_streams_counts_state_and_content_address(tmp_path):
    d = _trajectory_dir(tmp_path, [3, 5])
    s = stream_summary(d / "events.jsonl")
    assert s["completed"] == [3, 5]
    assert s["total_actions"] == 8
    assert s["state"] == "WIN"
    assert len(s["sha256"]) == 64


def test_malformed_logs_are_refused_never_admitted(tmp_path):
    bad_steps = _trajectory_dir(tmp_path, [3], contiguous=False)
    with pytest.raises(SchemaTraceError):
        stream_summary(bad_steps / "events.jsonl")


def test_win_with_unassigned_actions_is_refused(tmp_path):
    d = _trajectory_dir(tmp_path, [3], trailing_actions=2)
    with pytest.raises(SchemaTraceError):
        stream_summary(d / "events.jsonl")


def test_load_trajectory_rederives_the_grade(tmp_path):
    d = _trajectory_dir(tmp_path, [10, 20])
    traj = load_trajectory(d, {"zz99": [10, 20]})
    assert traj["game"] == "zz99"
    assert traj["model"] == "claude-fable-5"
    assert traj["effort"] == "max"
    assert traj["state"] == "WIN"
    assert traj["rhae"] == 100.0
    assert traj["per_level_actions"] == [10, 20]
    assert len(traj["events_sha256"]) == 64


def test_gradable_row_shape_and_seal(tmp_path):
    d = _trajectory_dir(tmp_path, [10, 20])
    row = to_gradable_row(load_trajectory(d, {"zz99": [10, 20]}))
    assert row["task_id"] == "arc-agi-3:zz99"
    assert row["source"] == "schema-harness.arc-agi-3/1"
    assert row["difficulty"] == "trajectory"
    assert row["grade"]["reward"] == 1.0        # RHAE/100, capped at game cap
    assert row["grade"]["label"] == "WIN"
    hidden = json.loads(row["hidden_tests"])
    assert hidden["baseline_actions"] == [10, 20]
    assert "rhae" in hidden["derivation"]
    solution = json.loads(row["solution"])
    assert solution["per_level_actions"] == [10, 20]
    assert row["oracle_ref"]                     # the events content-address


def test_recheck_matches_then_drifts_on_tamper(tmp_path):
    d = _trajectory_dir(tmp_path, [10, 20])
    baselines = {"zz99": [10, 20]}
    row = to_gradable_row(load_trajectory(d, baselines))
    ok = recheck(row, d / "events.jsonl", baselines)
    assert ok["witness"] == "MATCH" and ok["reasons"] == []
    # tamper: shave actions off the log to inflate efficiency
    events = (d / "events.jsonl").read_text(encoding="utf-8").splitlines()
    (d / "events.jsonl").write_text("\n".join(events[:-6] + events[-1:]),
                                    encoding="utf-8")
    bad = recheck(row, d / "events.jsonl", baselines)
    assert bad["witness"] == "DRIFT"
    assert bad["reasons"]
