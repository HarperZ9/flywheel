"""Count work, not verdict rows, with no model or network calls."""
import json
from types import SimpleNamespace

import pytest

from harness.local_finalizer_accounting import ExperimentAccounting, AccountingDurabilityError
from harness.local_finalizer_accounting_verify import aggregate_accounting
from harness.local_finalizer_experiment import FIXED_PARAMS, run_candidate_prefix_experiment
from harness.observed_proposer import ObservedProposer


def task(name="one"):
    return {"task_id": name, "task_set_id": "calibration", "raw_prompt_sha256": "a" * 64,
            "visible_input_sha256s": {"fixture.json": "b" * 64}, "expected_artifacts": []}


def invoke(stage, count=1, failure=False, usage=None):
    class Proposer:
        model_ref = "fake"

        def generate(self, *args, **kwargs):
            if failure:
                raise OSError("private error text")
            return SimpleNamespace(usage=usage, served_model="fake", model_ref="fake")

    stage.instrument()
    proposer = ObservedProposer(Proposer(), 60, lambda: 0, observer=stage)
    for _ in range(count):
        proposer.generate("private prompt", max_new_tokens=16)


def run(tmp_path, tasks=None, accounting=None, prefix_fail=False):
    tasks = tasks or [task()]
    accounting = accounting or ExperimentAccounting()

    def candidate(t, params, path):
        invoke(accounting.stage(t["task_id"], "normal"), 2, prefix_fail)
        return {"state": "returned", "eligible": True, "selected_text": "same",
                "candidate_state": "eligible_no_test_no_criteria", "normal_call_count": 999}

    def finalizer(arm, t, candidate, params, path):
        invoke(accounting.stage(t["task_id"], arm))
        return {"state": "returned", "selected_text": "same"}

    result = run_candidate_prefix_experiment(tasks, tmp_path / "run", FIXED_PARAMS,
        candidate_runner=candidate, finalizer_runner=finalizer,
        score_runner=lambda *args: ("pass", []), accounting=accounting)
    return result, accounting


def test_shared_prefix_counted_once_not_omitted_or_tripled(tmp_path):
    result, account = run(tmp_path, [task("one"), task("two"), task("three")])
    counts = result["invocation_accounting"]
    assert len(result["rows"]) == 9
    assert counts["known_started_invocations"] == counts["total_started_invocations"] == 12
    assert counts["normal_started_invocations"] == 6
    assert counts["finalizer_started_invocations"] == 6
    assert counts["accounting_complete"] is True
    assert counts["request_send_attempts"] is None
    assert len({r["prefix_id"] for r in result["rows"]}) == 3
    assert counts["requested_output_token_ceiling"] == 192
    assert counts["native_usage"]["eval_count"]["total"] is None
    assert "private prompt" not in json.dumps(account.receipts())


def test_same_candidate_distinct_tasks_runs_and_permutation(tmp_path):
    _, first = run(tmp_path / "first", [task("one"), task("two")])
    _, second = run(tmp_path / "second", [task("one"), task("two")])
    assert first.manifest["run_id"] != second.manifest["run_id"]
    assert aggregate_accounting(first.manifest, first.receipts()) == aggregate_accounting(
        first.manifest, list(reversed(first.receipts())))
    with pytest.raises(ValueError, match="task"):
        run(tmp_path / "duplicate", [task("one"), task("ONE")])


def test_prefix_failure_count_retained_and_arms_explicitly_skipped(tmp_path):
    result, account = run(tmp_path, prefix_fail=True)
    counts = result["invocation_accounting"]
    assert counts["total_started_invocations"] == 1
    assert counts["raised_invocations"] == 1
    assert len(result["rows"]) == 3
    assert {r["disposition"] for r in account.receipts()} == {
        "raised", "skipped_candidate_unavailable"}


def test_missing_stage_is_not_skip_and_legacy_callbacks_are_unknown(tmp_path):
    _, account = run(tmp_path / "first")
    reduced = aggregate_accounting(account.manifest, account.receipts()[:-1])
    assert reduced["accounting_complete"] is False
    assert reduced["total_started_invocations"] is None
    result = run_candidate_prefix_experiment([task()], tmp_path / "legacy", FIXED_PARAMS,
        candidate_runner=lambda *a: {"state": "returned", "eligible": True,
            "selected_text": "same", "normal_call_count": 8},
        finalizer_runner=lambda *a: {"state": "returned", "selected_text": "same"},
        score_runner=lambda *a: ("pass", []), accounting=ExperimentAccounting())
    assert result["invocation_accounting"]["total_started_invocations"] is None


def test_context_preflight_has_runner_entry_but_no_invocation(tmp_path):
    account = ExperimentAccounting()

    def finalizer(arm, t, *args):
        account.stage(t["task_id"], arm).instrument()
        return {"state": "context_not_admitted"}

    result = run_candidate_prefix_experiment([task()], tmp_path / "run", FIXED_PARAMS,
        candidate_runner=lambda t, *args: (invoke(account.stage(t["task_id"], "normal")),
            {"state": "returned", "eligible": True, "selected_text": "x"})[1],
        finalizer_runner=finalizer, score_runner=lambda *a: ("pass", []), accounting=account)
    assert result["invocation_accounting"]["total_started_invocations"] == 1
    assert result["invocation_accounting"]["finalizer_started_invocations"] == 0


def test_fatal_sink_failure_survives_normalized_error_and_stops_later_tasks(tmp_path, monkeypatch):
    account = ExperimentAccounting()
    entered = []

    def candidate(t, *args):
        entered.append(t["task_id"])
        stage = account.stage(t["task_id"], "normal")
        stage.instrument()
        monkeypatch.setattr(stage, "_append", lambda event: (_ for _ in ()).throw(OSError("disk")))
        try:
            invoke(stage)
        except AccountingDurabilityError:
            return {"state": "transport_error"}  # simulate finalizer normalization

    with pytest.raises(AccountingDurabilityError):
        run_candidate_prefix_experiment([task("one"), task("two")], tmp_path / "run", FIXED_PARAMS,
            candidate_runner=candidate, finalizer_runner=lambda *a: pytest.fail("must not dispatch"),
            accounting=account)
    assert entered == ["one"]
