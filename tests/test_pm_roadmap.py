"""The PM roadmap: goals, their decomposed child work, and each child's
verification status on one readable page. V1 reads what the platform
already seals -- swarm receipts and bound skill gates -- and states its
own limits on the page itself."""
from pathlib import Path

from harness.pm_roadmap import build_pm_roadmap, journey_row, render_markdown


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


def _journey_projection(stage="running", checks=None):
    return {
        "schema": "flywheel.evidence-journey-projection/v2",
        "journey_ref": "jrn_" + "a" * 32,
        "event_head_sha256": "c" * 64,
        "stage": stage,
        "conclusion": None,
        "checks": checks if checks is not None else [
            {"check_id": "chk_1", "claim_id": "clm_1", "verdict": "PASS",
             "receipt_state": "MATCH", "numerator": 3, "denominator": 3,
             "does_not_prove": ""},
            {"check_id": "chk_2", "claim_id": "clm_1", "verdict": "UNDECIDED",
             "receipt_state": "present_unchecked", "numerator": 0,
             "denominator": 2, "does_not_prove": ""},
        ],
    }


def test_journey_rows_carry_stage_and_check_verification():
    doc = build_pm_roadmap(swarms=[], skills=[],
                           journeys=[journey_row(_journey_projection(),
                                                 goal="ship the exporter")],
                           generated_at="t")
    goal = doc["goals"][0]
    assert goal["kind"] == "journey"
    assert goal["stage"] == "running"
    assert goal["verified_children"] == "1 of 2"
    assert goal["verdict"] is None
    assert doc["verification"]["journeys"] == 1


def test_concluded_journey_verdict_comes_from_its_conclusion():
    proj = _journey_projection(stage="concluded")
    row = journey_row(proj, goal="g")
    assert row["verdict"] is None
    proj["conclusion"] = {"verdict": "PASS"}
    row = journey_row(proj, goal="g")
    assert row["verdict"] == "PASS"


def test_route_ingests_a_real_journey_store(tmp_path: Path):
    import json
    from harness.journey_store import JourneyStore, MutationCommand

    state = tmp_path / "home" / "state"
    store = JourneyStore(state)
    owner = "owner_" + "a" * 8
    store.create(MutationCommand(
        owner_ref=owner, journey_ref="jrn_" + "b" * 32,
        expected_event_head=None, client_request_id="crq-1",
        operation="intake",
        body={"legacy_label": None, "goal": "land the finance pack",
              "intake": {}, "occurred_at": "2026-08-25T00:00:00Z"}))

    sdir = tmp_path / "subagents" / ("swarm_" + "a" * 12)
    sdir.mkdir(parents=True)
    (sdir / "swarm.json").write_text(json.dumps(_sealed_swarm()),
                                     encoding="utf-8")

    from harness.pm_roadmap_route import handle_pm_get
    body, code = handle_pm_get(
        "/api/pm/roadmap", run_root=tmp_path, clock=lambda: "t",
        journeys_state_root=state, owner_ref=owner)
    assert code == 200
    goals = body["roadmap"]["goals"]
    kinds = {g["kind"] for g in goals}
    assert kinds == {"swarm", "journey"}
    jrow = next(g for g in goals if g["kind"] == "journey")
    assert jrow["goal"] == "land the finance pack"
    assert jrow["stage"] == "intake"
    assert "journeys tracked: 1" in body["one_page"]

    # a store that cannot be read degrades to a note, never a crash
    body2, code = handle_pm_get(
        "/api/pm/roadmap", run_root=tmp_path, clock=lambda: "t",
        journeys_state_root=tmp_path / "nowhere", owner_ref="nobody")
    assert code == 200
    assert all(g["kind"] == "swarm" for g in body2["roadmap"]["goals"])
