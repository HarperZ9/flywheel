"""A historical retry diagnostic must not become a verified uplift claim."""
import hashlib
import json
import pytest
from types import SimpleNamespace

from harness.uplift_bench import SCHEMA, bench_summary, run_uplift_bench


class Proposer:
    def generate(self, prompt, *, seed, **kwargs):
        return SimpleNamespace(text="good" if seed else "bad")


def test_large_retry_delta_is_not_evidence_of_workflow_uplift(tmp_path):
    tasks = tmp_path / "tasks.jsonl"
    tasks.write_text('\n'.join(json.dumps({"task_id": str(i), "prompt": "task"})
                               for i in range(40)), encoding="utf-8")
    doc = run_uplift_bench(tasks, ["model"], n_candidates=2,
                           oracle=lambda text, task: text == "good",
                           proposers={"model": Proposer})
    delta = doc["deltas"][0]
    assert delta["uplift"] == 1.0  # Preserve the measured descriptive difference.
    assert delta["claim_status"] == "not_established"
    assert delta["newcombe_95"] is None
    assert delta["includes_zero"] is None
    assert "selector" in delta["note"]
    assert doc["analysis_kind"] == "legacy_retry_diagnostic"


def test_failures_remain_in_confirmed_completion_denominator(tmp_path):
    tasks = tmp_path / "tasks.jsonl"
    tasks.write_text('\n'.join(json.dumps({"task_id": str(i), "prompt": "task"})
                               for i in range(4)), encoding="utf-8")
    doc = run_uplift_bench(tasks, ["model"], n_candidates=2,
                           oracle=lambda text, task: True if task['task_id']=='0' else None,
                           proposers={"model": Proposer})
    for row in doc["rows"]:
        assert row["pass_rate"] == 1.0  # Conditional rate remains available.
        assert row["confirmed_completion_rate"] == .25
        assert row["completion_denominator"] == 4


def test_historical_claim_is_reinterpreted_without_rewriting_evidence(tmp_path):
    dest = tmp_path / "artifacts" / "uplift" / "old.json"
    dest.parent.mkdir(parents=True)
    dest.write_text(json.dumps({"schema": SCHEMA, "rows": [], "deltas": [{
        "provider": "old", "uplift": .8, "newcombe_95": [.6, .9],
        "includes_zero": False, "note": "measured uplift"}]}), encoding="utf-8")
    before = hashlib.sha256(dest.read_bytes()).hexdigest()
    summary = bench_summary(tmp_path)
    for delta in [summary["latest"]["deltas"][0], summary["runs"][0]["deltas"][0]]:
        assert delta["claim_status"] == "not_established"
        assert delta["newcombe_95"] is None
    assert hashlib.sha256(dest.read_bytes()).hexdigest() == before


def test_live_runner_materializes_only_under_explicit_work_root(tmp_path, monkeypatch):
    from scripts import run_uplift_live as runner
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(runner, "ROOT", repo)
    seen = []

    def fake_run(tasks, providers, **kwargs):
        seen.append(tasks.resolve())
        return {"rows": [], "deltas": [], "artifact_path": str(kwargs["out_path"])}

    monkeypatch.setattr(runner, "run_uplift_bench", fake_run)
    work = tmp_path / "private-work"
    assert runner.main(["--work-root", str(work), "--out", str(tmp_path/'report.json'),
                        "--max-tasks", "1"]) == 0
    assert len(seen) == 1 and seen[0].is_relative_to(work)
    assert len(seen[0].read_text(encoding="utf-8").splitlines()) == 1
    assert not (repo / "artifacts").exists()


@pytest.mark.parametrize('bad_line', [
    'not-json', 'null', '{"task_id":"a","prompt":"other"}',
])
def test_invalid_or_duplicate_task_cannot_silently_shrink_scope(tmp_path, bad_line):
    path = tmp_path / 'tasks.jsonl'
    path.write_text('{"task_id":"a","prompt":"task"}\n'+bad_line,
                    encoding='utf-8')
    doc = run_uplift_bench(path, ['model'], oracle=lambda c, t: True,
                           proposers={'model': lambda: pytest.fail('generation started')})
    assert 'error' in doc


@pytest.mark.parametrize('interval_flag', [False, None])
def test_frontier_cannot_promote_legacy_or_missing_interval(tmp_path, interval_flag):
    from harness.frontier import frontier_table
    dest = tmp_path / 'artifacts' / 'uplift' / 'run.json'
    dest.parent.mkdir(parents=True)
    dest.write_text(json.dumps({'schema': SCHEMA, 'rows': [], 'deltas': [
        {'provider': 'model', 'includes_zero': interval_flag}]}), encoding='utf-8')
    row = frontier_table(tmp_path, probes=[{'endpoint': 'model'}])['rows'][0]
    assert row['uplift_separated'] is False
    assert row['claim_status'] == 'not_established'
