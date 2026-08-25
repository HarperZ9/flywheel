"""The skill routes: listing bound skills and binding an admitted
lesson to passing gate evidence. The registry holds sealed rows only."""
import json

from harness.lesson import STATUS_ADMITTED, build_lesson
from harness.skill_route import handle_skills_get, handle_skills_post


def _lesson():
    return build_lesson(
        kind="pattern", source_organ="flywheel",
        source_refs=[{"organ": "flywheel", "ref": "r/x",
                      "digest": "a" * 64}],
        claim="prefer exact grants when spawning work",
        evidence_class="repeated", repetition_count=2,
        scope="harness", status=STATUS_ADMITTED,
        created_at="2026-08-24T00:00:00Z")


def _bench():
    return {"schema": "flywheel.verified-bench/v1",
            "bench_sha256": "b" * 64,
            "denominator": {"attempts": 1},
            "attempts": [{"task_id": "t0", "endpoint": "dry",
                          "gate_pass": True}]}


def test_bind_round_trip_and_listing(tmp_path):
    lesson = _lesson()
    sent, code = handle_skills_post(
        "/api/skills/bind", {"lesson": lesson, "evidence": _bench()},
        run_root=tmp_path, clock=lambda: "2026-08-24T01:00:00Z")
    assert code == 200
    assert sent["skill_gate"]["all_passed"] is True

    listed, code = handle_skills_get("/api/skills", run_root=tmp_path)
    assert code == 200
    assert listed["count"] == 1
    assert listed["skills"][0]["lesson_id"] == lesson["lesson_id"]


def test_bind_refuses_unearned_evidence(tmp_path):
    failing = {"schema": "flywheel.verified-bench/v1",
               "bench_sha256": "b" * 64,
               "denominator": {"attempts": 1},
               "attempts": [{"task_id": "t0", "endpoint": "dry",
                             "gate_pass": False}]}
    _, code = handle_skills_post(
        "/api/skills/bind", {"lesson": _lesson(), "evidence": failing},
        run_root=tmp_path)
    assert code == 422
    listed, _ = handle_skills_get("/api/skills", run_root=tmp_path)
    assert listed["count"] == 0


def test_unknown_skill_route_is_404(tmp_path):
    _, code = handle_skills_post("/api/skills/explode", {},
                                 run_root=tmp_path)
    assert code == 404
    _, code = handle_skills_get("/api/skills/nope", run_root=tmp_path)
    assert code == 404


def test_registry_survives_a_reload(tmp_path):
    lesson = _lesson()
    handle_skills_post("/api/skills/bind",
                       {"lesson": lesson, "evidence": _bench()},
                       run_root=tmp_path, clock=lambda: "t")
    raw = (tmp_path / "skills" / "gates.jsonl").read_text(encoding="utf-8")
    assert len(raw.strip().splitlines()) == 1
    row = json.loads(raw)
    assert row["schema"] == "flywheel.skill-gate/v1"
