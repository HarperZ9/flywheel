"""Skill evidence consistency; local fixtures do not authenticate evaluators."""
import json
from pathlib import Path

import pytest

from harness.lesson import (
    MATCH,
    STATUS_ADMITTED,
    STATUS_SURFACED,
    build_lesson,
)
from harness.lesson_store import LessonStore
from harness.trace_bench import regression_report
from harness.verified_bench import run_benchmark
from harness.skill_gate import (
    DRIFT,
    build_skill_gate,
    load_skill_gates,
    save_skill_gates,
    verify_skill_gate,
)


def _lesson(status=STATUS_ADMITTED):
    return build_lesson(
        kind="pattern",
        source_organ="flywheel",
        source_refs=[{"organ": "flywheel", "ref": "runs/abc",
                      "digest": "a" * 64}],
        claim="prefer the exact-grant path when spawning work",
        evidence_class="repeated",
        repetition_count=3,
        scope="harness",
        status=status,
        created_at="2026-08-24T00:00:00Z",
    )


def _bench(passing=True, attempts=2):
    return run_benchmark(
        tasks=[{"task_id": f"trace-{i}", "prompt": "fixture",
                "gate_cmd": "fixed-fixture"} for i in range(attempts)],
        endpoints=["dry"], created_at="fixture",
        propose=lambda endpoint, prompt, seed: "fixture-proposal",
        run_gate=lambda command, proposal: {"passed": passing,
                                            "gate_ref": "fixture-gate"})


def _store(lesson):
    store = LessonStore()
    store.append(dict(lesson, seq=0, prev_hash=store.lessons[-1][
        "seal_hash"] if len(store) else "0" * 64))
    return store


def test_an_admitted_lesson_binds_a_passing_bench():
    lesson = _lesson()
    store = _store(lesson)
    binding = build_skill_gate(
        lesson=store.latest_for(lesson["lesson_id"]),
        evidence=_bench(), bound_at="2026-08-24T01:00:00Z")
    assert binding["schema"] == "flywheel.skill-gate/v2"
    assert binding["all_passed"] is True
    assert binding["tasks_bound"] == 2
    assert len(binding["evidence_sha256"]) == 64
    assert verify_skill_gate(binding)["verdict"] == MATCH


def test_a_failing_attempt_refuses_the_bind():
    store = _store(_lesson())
    with pytest.raises(ValueError):
        build_skill_gate(lesson=store.latest_for(
            _lesson()["lesson_id"]), evidence=_bench(passing=False),
        bound_at="t")


def test_a_surfaced_lesson_is_not_yet_a_skill():
    surfaced = _lesson(status=STATUS_SURFACED)
    store = _store(surfaced)
    with pytest.raises(ValueError):
        build_skill_gate(
            lesson=store.latest_for(surfaced["lesson_id"]),
            evidence=_bench(), bound_at="t")


def test_zero_regressions_bind_and_one_regression_refuses():
    store = _store(_lesson())
    latest = store.latest_for(_lesson()["lesson_id"])
    prior, current = _bench(), _bench()
    ok = build_skill_gate(lesson=latest, evidence=regression_report(prior, current),
                         prior_bench=prior, current_bench=current, bound_at="t")
    assert ok["evidence_kind"] == "trace_regression"
    with pytest.raises(ValueError):
        build_skill_gate(lesson=latest, evidence=regression_report(prior, _bench(False)),
                         prior_bench=prior, current_bench=_bench(False), bound_at="t")


def test_verify_catches_a_tampered_binding():
    store = _store(_lesson())
    binding = build_skill_gate(
        lesson=store.latest_for(_lesson()["lesson_id"]),
        evidence=_bench(), bound_at="t")
    tampered = dict(binding, tasks_bound=99)
    assert verify_skill_gate(tampered)["verdict"] == DRIFT
    assert verify_skill_gate(dict(binding,
                                  evidence_sha256="0" * 64))["verdict"] == DRIFT


def test_registry_round_trip_validates_rows(tmp_path: Path):
    store = _store(_lesson())
    binding = build_skill_gate(
        lesson=store.latest_for(_lesson()["lesson_id"]),
        evidence=_bench(), bound_at="t")
    path = save_skill_gates([binding], registry_path=tmp_path / "gates.jsonl")
    rows = load_skill_gates(path)
    assert [r["lesson_id"] for r in rows] == [binding["lesson_id"]]
    (tmp_path / "bad.jsonl").write_text(
        json.dumps({"schema": "flywheel.skill-gate/v1"}) + "\n",
        encoding="utf-8")
    with pytest.raises(ValueError):
        load_skill_gates(tmp_path / "bad.jsonl")
