"""The PM roadmap: goals, their decomposed child work, and each child's
verification status on one readable page. V1 reads what the platform
already seals -- swarm receipts and bound skill gates -- and states its
own limits on the page itself."""
from pathlib import Path

from harness.pm_roadmap import build_pm_roadmap, render_markdown


def _sealed_swarm(swarm_id="swarm_" + "a" * 12, satisfied=True):
    return {
        "schema": "flywheel.subagent-swarm/v1",
        "swarm_id": swarm_id,
        "goal_sha256": "b" * 64,
        "endpoint": "dry",
        "quorum_policy": "majority",
        "required": 2, "completed": 2 if satisfied else 0, "total": 2,
        "verdict": "satisfied" if satisfied else "unsatisfied",
        "created_at": "2026-08-24T00:00:00Z",
        "finished_at": "2026-08-24T00:05:00Z",
        "event_blocked": False,
        "children": [
            {"child_id": "sa_1", "role": "explore", "status": "completed"},
            {"child_id": "sa_2", "role": "verify", "status":
             "completed" if satisfied else "cancelled"},
        ],
    }


def test_roadmap_collects_goals_and_the_verification_floor():
    doc = build_pm_roadmap(
        swarms=[_sealed_swarm(), _sealed_swarm("swarm_" + "c" * 12,
                                               satisfied=False)],
        skills=[{"lesson_id": "x", "gate_sha256": "d" * 64}],
        generated_at="2026-08-24T09:00:00Z")
    assert doc["schema"] == "flywheel.pm-roadmap/v1"
    assert len(doc["goals"]) == 2
    satisfied = doc["goals"][0]
    assert satisfied["verdict"] == "satisfied"
    assert satisfied["verified_children"] == "2 of 2"
    assert doc["verification"]["skills_bound"] == 1


def test_running_and_detached_swarms_appear_with_honest_states():
    running = {"swarm_id": "swarm_r", "status": "running", "children": []}
    doc = build_pm_roadmap(swarms=[running], skills=[],
                           generated_at="t")
    assert doc["goals"][0]["state"] == "running"
    assert doc["goals"][0]["verdict"] is None


def test_one_page_renders_without_claim_language():
    page = render_markdown(build_pm_roadmap(
        swarms=[_sealed_swarm()], skills=[], generated_at="t"))
    assert "# Roadmap" in page
    assert "| swarm_aaaaaaaa..." in page  # ids appear as short refs
    assert "satisfied" in page
    assert "does not prove" in page  # the page carries its own limits
    for banned in ("optimal", "guaranteed", "best-in-class"):
        assert banned not in page


def test_route_serves_the_roadmap_from_a_run_root(tmp_path: Path):
    import json
    sdir = tmp_path / "subagents" / ("swarm_" + "a" * 12)
    sdir.mkdir(parents=True)
    (sdir / "swarm.json").write_text(json.dumps(_sealed_swarm()),
                                     encoding="utf-8")
    from harness.pm_roadmap_route import handle_pm_get
    body, code = handle_pm_get("/api/pm/roadmap", run_root=tmp_path,
                               clock=lambda: "2026-08-24T09:00:00Z")
    assert code == 200
    assert body["roadmap"]["goals"][0]["total"] == 2
    _, code = handle_pm_get("/api/pm/nope", run_root=tmp_path,
                            clock=lambda: "t")
    assert code == 404
