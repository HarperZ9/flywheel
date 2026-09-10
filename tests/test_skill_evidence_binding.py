"""False-success controls for skill evidence, using the real bench producer."""
from copy import deepcopy

import pytest

from harness.evidence_json import canonical_sha256
from harness.skill_gate import build_skill_gate, verify_skill_gate
from harness.skill_route import handle_skills_get, handle_skills_post
from harness.trace_bench import regression_report
from harness.verified_bench import run_benchmark
from tests.test_skill_gate import _lesson


def bench(*, passing=True, seeds=(3, 8), control=None):
    return run_benchmark(
        tasks=[{"task_id": t, "prompt": t, "gate_cmd": "fixed-local-check"}
               for t in ("a", "b")], endpoints=["local"], seeds=seeds,
        randomness_control=control, created_at="fixture",
        propose=lambda endpoint, prompt, seed: prompt,
        run_gate=lambda cmd, proposal: {"passed": passing,
                                       "gate_ref": "local-owned-fixture"})


def seal(doc, field):
    doc[field] = canonical_sha256({k: v for k, v in doc.items() if k != field})
    return doc


def bind(evidence=None, **kwargs):
    return build_skill_gate(lesson=_lesson(), evidence=evidence or bench(),
                            bound_at="fixture", **kwargs)


def test_real_producer_binds_unique_tasks_and_attempts_with_honest_assurance():
    evidence = bench(control={"local": "unsupported"})
    row = bind(evidence)
    assert row["schema"] == "flywheel.skill-gate/v2"
    assert row["tasks_bound"] == 2
    assert row["attempts_bound"] == 4
    result = verify_skill_gate(row, evidence=evidence)
    assert result["verdict"] == "MATCH"
    assert result["source_binding"] == "MATCH"
    assert result["independent_evaluation"] == "UNVERIFIED"
    assert result["procedure_application"] == "UNKNOWN"


@pytest.mark.parametrize("damage", [
    lambda b: b.update(bench_sha256="b" * 64),
    lambda b: b["denominator"].update(attempts=999),
    lambda b: b["denominator"].update(tasks=True),
    lambda b: b["attempts"][0].pop("task_id"),
    lambda b: b["attempts"].__setitem__(0, None),
    lambda b: b["attempts"][0].update(task_id=""),
    lambda b: b["attempts"][0].update(endpoint="other"),
    lambda b: b["attempts"][0].update(repetition=1),
    lambda b: b["attempts"][0].update(seed=99),
    lambda b: b["attempts"][0].update(seed=True),
    lambda b: b["attempts"][0].update(proposed_sha256="wrong"),
    lambda b: b["attempts"][0].update(gate_ref=""),
    lambda b: b["attempts"][0].update(gate_pass=1),
    lambda b: b["attempts"][0].update(gate_cmd="different-gate"),
    lambda b: b["attempts"].pop(),
])
def test_malformed_or_resealed_contradictory_bench_is_rejected(damage):
    evidence = bench()
    damage(evidence)
    if evidence["bench_sha256"] != "b" * 64:
        seal(evidence, "bench_sha256")
    with pytest.raises(ValueError):
        bind(evidence)


def test_resealed_projection_contradiction_is_not_a_match():
    row = bind()
    row["attempts_bound"] = 999
    seal(row, "gate_sha256")
    assert verify_skill_gate(row)["verdict"] == "DRIFT"


def test_valid_but_different_source_is_not_the_bound_source():
    row = bind()
    other = bench(seeds=(1, 2))
    assert verify_skill_gate(row, evidence=other)["verdict"] == "DRIFT"


def test_report_requires_original_benches_and_rejects_failed_stable():
    bad = bench(passing=False, seeds=(3,))
    report = regression_report(bad, bad)
    assert report["regressions"] == []
    with pytest.raises(ValueError):
        bind(report)
    with pytest.raises(ValueError):
        bind(report, prior_bench=bad, current_bench=bad)


def test_trace_report_binds_exact_single_replicate_sources():
    prior, current = bench(passing=False, seeds=(3,)), bench(seeds=(3,))
    report = regression_report(prior, current)
    row = bind(report, prior_bench=prior, current_bench=current)
    assert row["tasks_bound"] == 2
    assert verify_skill_gate(row, evidence=report, prior_bench=prior,
                             current_bench=current)["source_binding"] == "MATCH"
    row["evidence_sha256"] = "e" * 64
    seal(row, "gate_sha256")
    assert verify_skill_gate(row)["verdict"] == "DRIFT"
    report["stable"] = 99
    with pytest.raises(ValueError):
        bind(report, prior_bench=prior, current_bench=current)


def test_trace_replicate_collapse_and_removed_tasks_refuse():
    current = bench()
    with pytest.raises(ValueError):
        bind(regression_report(current, current), prior_bench=current,
             current_bench=current)
    prior = bench(seeds=(3,))
    smaller = deepcopy(prior)
    smaller["attempts"] = smaller["attempts"][:1]
    smaller["denominator"].update(tasks=1, attempts=1)
    seal(smaller, "bench_sha256")
    with pytest.raises(ValueError):
        bind(regression_report(prior, smaller), prior_bench=prior,
             current_bench=smaller)


def test_legacy_rows_remain_unchanged_but_are_explicitly_unverified(tmp_path):
    import json
    row = {"schema": "flywheel.skill-gate/v1", "lesson_id": "a" * 64,
           "lesson_seal_hash": "a" * 64, "evidence_kind": "verified_bench",
           "evidence_sha256": "b" * 64, "tasks_bound": 1,
           "all_passed": True, "bound_at": "historic"}
    seal(row, "gate_sha256")
    path = tmp_path / "skills" / "gates.jsonl"
    path.parent.mkdir()
    path.write_text(json.dumps(row), encoding="utf-8")
    before = path.read_bytes()
    response, code = handle_skills_get("/api/skills", run_root=tmp_path)
    assert code == 200
    assert response["skills"] == [row]
    assert response["assurance"][row["gate_sha256"]]["verdict"] == "UNVERIFIED"
    assert path.read_bytes() == before


def test_bind_does_not_execute_request_supplied_commands(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("admission executed a caller command")
    monkeypatch.setattr("subprocess.run", forbidden)
    response, code = handle_skills_post(
        "/api/skills/bind", {"lesson": _lesson(), "evidence": bench()},
        run_root=tmp_path)
    assert code == 200
    assert response["assurance"]["independent_evaluation"] == "UNVERIFIED"


def test_fixed_local_checker_produces_usable_evidence_and_wrong_proposal_fails(tmp_path):
    import shlex
    import sys
    from harness.verified_bench import subprocess_gate

    # Fixed test-owned evaluator, never selected from the bind request.
    command = shlex.join([sys.executable, "-c",
        "from pathlib import Path; import sys; "
        "sys.exit(0 if Path('PROPOSED.md').read_text() == 'answer=7' else 1)"])
    def run(proposal):
        return run_benchmark(
            tasks=[{"task_id": "fixed-check", "prompt": "fixture", "gate_cmd": command}],
            endpoints=["synthetic-local"], created_at="fixture",
            propose=lambda *args: proposal,
            run_gate=lambda cmd, value: subprocess_gate(cmd, value, workspace=tmp_path))

    evidence = run("answer=7")
    assert evidence["attempts"][0]["gate_pass"] is True
    assert evidence["attempts"][0]["proposed_sha256"] == canonical_sha256("answer=7")
    row = bind(evidence)
    assert verify_skill_gate(row, evidence=evidence)["source_binding"] == "MATCH"
    assert row["independent_evaluation"] == "UNVERIFIED"
    wrong = run("answer=8")
    assert wrong["attempts"][0]["gate_pass"] is False
    with pytest.raises(ValueError):
        bind(wrong)


def test_coherently_fabricated_bench_is_not_claimed_authenticated():
    # All supplied flags/seals can be invented consistently. Admission cannot
    # infer execution, authenticity, or use of the admitted lesson from them.
    invented = bench(passing=False)
    for attempt in invented["attempts"]:
        attempt["gate_pass"] = True
    seal(invented, "bench_sha256")
    assurance = verify_skill_gate(bind(invented), evidence=invented)
    assert assurance["verdict"] == "MATCH"
    assert assurance["independent_evaluation"] == "UNVERIFIED"
    assert assurance["procedure_application"] == "UNKNOWN"


@pytest.mark.parametrize("evidence", [
    {"schema": "flywheel.verified-bench/v1", "attempts": [None]},
    {"schema": "flywheel.trace-regression/v1", "stable": 99, "regressions": []},
    {"schema": ["not-a-schema"]},
])
def test_invalid_route_evidence_is_422_and_does_not_write(tmp_path, evidence):
    _, code = handle_skills_post("/api/skills/bind",
        {"lesson": _lesson(), "evidence": evidence}, run_root=tmp_path)
    assert code == 422
    assert not (tmp_path / "skills" / "gates.jsonl").exists()


def test_new_v2_binding_can_append_beside_unmodified_legacy_payload(tmp_path):
    import json
    from harness.skill_gate import load_skill_gates, save_skill_gates
    old = {"schema": "flywheel.skill-gate/v1", "lesson_id": "a" * 64,
           "lesson_seal_hash": "a" * 64, "evidence_kind": "verified_bench",
           "evidence_sha256": "b" * 64, "tasks_bound": 1,
           "all_passed": True, "bound_at": "historic"}
    seal(old, "gate_sha256")
    path = save_skill_gates([old], registry_path=tmp_path / "skills" / "gates.jsonl")
    response, code = handle_skills_post("/api/skills/bind",
        {"lesson": _lesson(), "evidence": bench()}, run_root=tmp_path)
    assert code == 200
    rows = load_skill_gates(path)
    assert rows == [old, response["skill_gate"]]
    assert json.loads(path.read_text().splitlines()[0]) == old
