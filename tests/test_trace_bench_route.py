"""The trace-bench route: stored failures become the regression suite,
and the prior bench is compared so a fix is provable and a regression
is named."""
import json
from pathlib import Path

import pytest

from harness.trace_bench_route import handle_bench_traces


class _Backend:
    name = "strong"

    def chat(self, messages, *, system, max_tokens, temperature, seed):
        # A proposer that "fixed" everything: every gate now passes.
        return {"text": "the fix", "model_ref": "strong:x", "seed": seed}


def _seed_runs(run_root: Path):
    from harness.eval_store import save_agent_run
    saved = []
    # Proposal-sensitive gates: the gate reads PROPOSED.md (which the
    # runner writes before running the command), so a changed proposer
    # genuinely changes the outcome.
    for doc in (
        {"goal": "fix the login bug", "verdict": "FAIL",
         "endpoint": "ox-alpha",
         "test_cmd": "python -c \"import sys; sys.exit("
                     "0 if 'fix' in open('PROPOSED.md', encoding='utf-8')"
                     ".read() else 3)\"",
         "steps": []},
        {"goal": "add the export button", "verdict": "PASS",
         "endpoint": "ox-alpha",
         "test_cmd": "python -c \"import sys; sys.exit("
                     "0 if 'fix' in open('PROPOSED.md', encoding='utf-8')"
                     ".read() else 3)\"",
         "steps": []},
    ):
        saved.append(save_agent_run(run_root, doc))
    return [s["run_id"] for s in saved]


    def test_failed_traces_become_the_regression_suite(tmp_path):
        run_ids = _seed_runs(tmp_path)
        body, code = handle_bench_traces(
            {"outcomes": ["FAIL"], "endpoints": ["strong"], "timeout_s": 60},
            run_root=tmp_path, build_endpoints=lambda **kw: [_Backend()])
        assert code == 200
        # Only the FAIL run entered the task set.
        assert body["tasks"] == 1
        assert body["bench"]["attempts"][0]["task_id"] == (
            "trace-" + run_ids[0])
        # The first run has no prior: the attempt is reported as new.
        assert body["regressions"]["new"] == [
            {"task_id": "trace-" + run_ids[0], "endpoint": "strong",
             "current": "PASS"}]

        # Second run over the same trace: the prior FAIL now passes with
        # this proposer, so the improvement is sealed by name.
        body2, code2 = handle_bench_traces(
            {"outcomes": ["FAIL"], "endpoints": ["strong"], "timeout_s": 60},
            run_root=tmp_path, build_endpoints=lambda **kw: [_Backend()])
        assert code2 == 200
        improvements = body2["regressions"]["improvements"]
        assert improvements and improvements[0]["current"] == "PASS"
        assert improvements[0]["task_id"] == "trace-" + run_ids[0]


def test_a_prior_bench_drives_regression_detection(tmp_path):
    _seed_runs(tmp_path)
    handle_bench_traces(
        {"outcomes": ["FAIL", "PASS"], "endpoints": ["strong"],
         "timeout_s": 60},
        run_root=tmp_path, build_endpoints=lambda **kw: [_Backend()])

    # Second run: a proposer that now BREAKS the previously-passing task.
    class _Broken(_Backend):
        def chat(self, messages, *, system, max_tokens, temperature, seed):
            return {"text": "broken", "model_ref": "strong:x",
                    "seed": seed}

    body, code = handle_bench_traces(
        {"outcomes": ["FAIL", "PASS"], "endpoints": ["strong"],
         "timeout_s": 60},
        run_root=tmp_path, build_endpoints=lambda **kw: [_Broken()])
    assert code == 200
    regressions = body["regressions"]["regressions"]
    assert regressions, "a previously-passing task now fails: named"
    assert regressions[0]["prior"] == "PASS"
    assert regressions[0]["current"] == "FAIL"


def test_no_matching_traces_is_a_typed_404(tmp_path):
    body, code = handle_bench_traces(
        {"outcomes": ["ABORTED"], "endpoints": ["strong"]},
        run_root=tmp_path, build_endpoints=lambda **kw: [_Backend()])
    assert code == 404
    assert body["error"]["code"] == "NO_TRACES"


def test_unreadable_run_ids_are_skipped_not_fatal(tmp_path):
    body, code = handle_bench_traces(
        {"run_ids": ["nope1234"], "outcomes": ["FAIL"],
         "endpoints": ["strong"]},
        run_root=tmp_path, build_endpoints=lambda **kw: [_Backend()])
    assert code == 404


def test_the_prior_bench_file_persists(tmp_path):
    _seed_runs(tmp_path)
    handle_bench_traces(
        {"outcomes": ["FAIL"], "endpoints": ["strong"], "timeout_s": 60},
        run_root=tmp_path, build_endpoints=lambda **kw: [_Backend()])
    assert (tmp_path / "bench" / "trace-bench-prior.json").is_file()
    assert (tmp_path / "bench" / "trace-tasks.jsonl").is_file()
