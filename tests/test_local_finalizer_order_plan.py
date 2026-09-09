import json

import pytest

from harness.cross_harness_artifacts import canonical_sha256
from harness.local_finalizer_experiment import FIXED_PARAMS, run_candidate_prefix_experiment


def _task(task_id):
    return {
        "task_set_id": "local_finalizer_heldout_revised_20260908",
        "task_id": task_id,
        "expected_artifacts": ["report.json"],
        "visible_input_sha256s": {"visible.json": "a" * 64},
        "oracle_input_sha256s": {"oracle.json": "b" * 64},
        "oracle": {},
        "prompt": "prompt",
        "raw_prompt_sha256": "c" * 64,
    }


def _candidate(task, params, out_dir):
    return {
        "state": "returned",
        "eligible": True,
        "candidate_state": "eligible_no_test_no_criteria",
        "selected_text": json.dumps({"artifacts": {"report.json": {"task_id": task["task_id"]}}}),
        "context": {"candidate_text": "candidate", "history": []},
        "workspace_root": out_dir,
        "tool_policy": {},
    }


def test_explicit_order_plan_executes_per_task_order_and_binds_receipts(tmp_path):
    tasks = [_task("lfh-015-evidence-bound-nonleaky"), _task("lfh-016-source-contradiction-nonleaky")]
    order_plan = {
        "schema": "harness.local-finalizer-candidate-prefix-order-plan/v1",
        "task_set_id": "local_finalizer_heldout_revised_20260908",
        "orders": {
            "lfh-015-evidence-bound-nonleaky": ["C", "A", "B"],
            "lfh-016-source-contradiction-nonleaky": ["C", "B", "A"],
        },
    }
    calls = []

    def finalizer(arm, task, candidate, params, out_dir):
        calls.append((task["task_id"], arm))
        return {"state": "returned", "selected_text": candidate["selected_text"],
                "request_body_sha256": f"{arm.lower()}" * 64}

    summary = run_candidate_prefix_experiment(
        tasks,
        tmp_path / "run",
        FIXED_PARAMS,
        candidate_runner=_candidate,
        finalizer_runner=finalizer,
        score_runner=lambda *args: ("pass", []),
        order_plan=order_plan,
    )

    rows = summary["rows"]
    expected = [("lfh-015-evidence-bound-nonleaky", "C"), ("lfh-015-evidence-bound-nonleaky", "A"),
                ("lfh-015-evidence-bound-nonleaky", "B"), ("lfh-016-source-contradiction-nonleaky", "C"),
                ("lfh-016-source-contradiction-nonleaky", "B"), ("lfh-016-source-contradiction-nonleaky", "A")]
    task_orders = order_plan["orders"]
    order_hash = canonical_sha256(task_orders)
    assert [(row["task_id"], row["arm"]) for row in rows] == expected
    assert calls == [("lfh-015-evidence-bound-nonleaky", "A"), ("lfh-015-evidence-bound-nonleaky", "B"),
                     ("lfh-016-source-contradiction-nonleaky", "B"), ("lfh-016-source-contradiction-nonleaky", "A")]
    assert [row["arm_order_index"] for row in rows] == [0, 1, 2, 0, 1, 2]
    assert {row["task_arm_order_sha256"] for row in rows} == {order_hash}
    assert summary["task_arm_orders"] == task_orders
    assert summary["task_arm_order_sha256"] == order_hash
    manifest = json.loads((tmp_path / "run" / "pre-run-manifest.json").read_text(encoding="utf-8"))
    assert manifest["task_arm_orders"] == task_orders
    assert manifest["task_arm_order_sha256"] == order_hash


@pytest.mark.parametrize("orders", [
    {},
    {"lfh-015-evidence-bound-nonleaky": ["C", "A", "B"], "extra": ["C", "A", "B"]},
    {"lfh-015-evidence-bound-nonleaky": ["C", "A", "A"]},
    {"lfh-015-evidence-bound-nonleaky": ["C", "A"]},
    {"lfh-015-evidence-bound-nonleaky": ["C", "A", "D"]},
    {"lfh-015-evidence-bound-nonleaky": "C,A,B"},
])
def test_order_plan_rejects_incomplete_or_non_permutation_orders(tmp_path, orders):
    with pytest.raises(ValueError, match="order plan"):
        run_candidate_prefix_experiment(
            [_task("lfh-015-evidence-bound-nonleaky")],
            tmp_path / "run",
            FIXED_PARAMS,
            candidate_runner=_candidate,
            finalizer_runner=lambda *args: {"state": "returned", "selected_text": ""},
            score_runner=lambda *args: ("pass", []),
            order_plan={"schema": "harness.local-finalizer-candidate-prefix-order-plan/v1",
                        "task_set_id": "local_finalizer_heldout_revised_20260908", "orders": orders},
        )
    assert not (tmp_path / "run").exists()


def test_order_plan_rejects_wrong_task_set_before_any_runner_call(tmp_path):
    calls = []

    with pytest.raises(ValueError, match="task_set_id"):
        run_candidate_prefix_experiment(
            [_task("lfh-015-evidence-bound-nonleaky")],
            tmp_path / "run",
            FIXED_PARAMS,
            candidate_runner=lambda *args: calls.append("candidate"),
            finalizer_runner=lambda *args: calls.append("finalizer"),
            score_runner=lambda *args: ("pass", []),
            order_plan={"schema": "harness.local-finalizer-candidate-prefix-order-plan/v1",
                        "task_set_id": "wrong_task_set",
                        "orders": {"lfh-015-evidence-bound-nonleaky": ["C", "A", "B"]}},
        )

    assert calls == []
    assert not (tmp_path / "run").exists()


def test_order_plan_rejects_mixed_task_sets_before_any_runner_call(tmp_path):
    calls = []
    tasks = [_task("lfh-015-evidence-bound-nonleaky"),
             {**_task("lfh-016-source-contradiction-nonleaky"), "task_set_id": "other_set"}]

    with pytest.raises(ValueError, match="task_set_id"):
        run_candidate_prefix_experiment(
            tasks,
            tmp_path / "run",
            FIXED_PARAMS,
            candidate_runner=lambda *args: calls.append("candidate"),
            finalizer_runner=lambda *args: calls.append("finalizer"),
            score_runner=lambda *args: ("pass", []),
            order_plan={"schema": "harness.local-finalizer-candidate-prefix-order-plan/v1",
                        "task_set_id": "local_finalizer_heldout_revised_20260908",
                        "orders": {"lfh-015-evidence-bound-nonleaky": ["C", "A", "B"],
                                   "lfh-016-source-contradiction-nonleaky": ["C", "B", "A"]}},
        )

    assert calls == []
    assert not (tmp_path / "run").exists()


@pytest.mark.parametrize(("task_set_id", "plan_task_set_id"), [
    (None, "local_finalizer_heldout_revised_20260908"),
    (7, "7"),
    ("local_finalizer_heldout_revised_20260908", None),
    ("local_finalizer_heldout_revised_20260908", 7),
])
def test_order_plan_rejects_non_string_task_set_ids_before_any_runner_call(tmp_path, task_set_id, plan_task_set_id):
    calls = []
    task = {**_task("lfh-015-evidence-bound-nonleaky"), "task_set_id": task_set_id}

    with pytest.raises(ValueError, match="task_set_id"):
        run_candidate_prefix_experiment(
            [task],
            tmp_path / "run",
            FIXED_PARAMS,
            candidate_runner=lambda *args: calls.append("candidate"),
            finalizer_runner=lambda *args: calls.append("finalizer"),
            score_runner=lambda *args: ("pass", []),
            order_plan={"schema": "harness.local-finalizer-candidate-prefix-order-plan/v1",
                        "task_set_id": plan_task_set_id,
                        "orders": {"lfh-015-evidence-bound-nonleaky": ["C", "A", "B"]}},
        )

    assert calls == []
    assert not (tmp_path / "run").exists()


def test_default_order_plan_preserves_cab_order(tmp_path):
    summary = run_candidate_prefix_experiment(
        [_task("lfh-015-evidence-bound-nonleaky")],
        tmp_path / "run",
        FIXED_PARAMS,
        candidate_runner=_candidate,
        finalizer_runner=lambda arm, task, candidate, params, out_dir: {
            "state": "returned", "selected_text": candidate["selected_text"]},
        score_runner=lambda *args: ("pass", []),
    )

    assert [row["arm"] for row in summary["rows"]] == ["C", "A", "B"]
    assert summary["task_arm_orders"] == {"lfh-015-evidence-bound-nonleaky": ["C", "A", "B"]}
