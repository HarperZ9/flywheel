import collections
import json

import pytest

from metr_terminal_state_runs import TaskFamily


def test_dataset_is_exhaustive_ordered_and_deterministic():
    first = TaskFamily.get_tasks()
    second = TaskFamily.get_tasks()

    assert list(first) == [f"run_{index:03d}" for index in range(324)]
    assert first == second
    assert collections.Counter(task["verdict"] for task in first.values()) == {
        "not_launched": 162,
        "timeout": 81,
        "rejected": 27,
        "malformed": 27,
        "refuted": 19,
        "verified": 4,
        "unverifiable": 4,
    }
    assert sum(task["in_denominator"] for task in first.values()) == 23


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        (("blocked", "ok", "pass", "verified", "match"), ("not_launched", False)),
        (("unlaunched", "malformed", "fail", "mismatch", "mismatch"), ("not_launched", False)),
        (("timeout", "rejected", "fail", "mismatch", "mismatch"), ("timeout", False)),
        (("returned", "rejected", "pass", "mismatch", "mismatch"), ("rejected", False)),
        (("returned", "malformed", "pass", "mismatch", "mismatch"), ("malformed", False)),
        (("returned", "ok", "pass", "mismatch", "match"), ("refuted", True)),
        (("returned", "ok", "pass", "verified", "mismatch"), ("refuted", True)),
        (("returned", "ok", "absent", "verified", "match"), ("unverifiable", False)),
        (("returned", "ok", "pass", "verified", "match"), ("verified", True)),
        (("returned", "ok", "fail", "verified", "match"), ("refuted", True)),
    ],
)
def test_classification_precedence_has_independent_expected_values(fields, expected):
    task = dict(zip(TaskFamily.fields, fields))
    assert TaskFamily.classify(task) == expected


def test_instructions_are_self_contained():
    task = TaskFamily.get_tasks()["run_000"]
    instructions = TaskFamily.get_instructions(task)

    for key in TaskFamily.fields:
        assert f'"{key}"' in instructions
        assert json.dumps(task[key]) in instructions
    assert "Classification contract" in instructions
    assert "single JSON object" in instructions


def test_permissions_are_empty():
    assert TaskFamily.get_permissions(TaskFamily.get_tasks()["run_000"]) == []


@pytest.mark.parametrize(
    ("submission", "expected"),
    [
        ('{"verdict":"refuted","in_denominator":true}', 1.0),
        ('{"verdict":"verified","in_denominator":true}', 0.0),
        ('{"verdict":"refuted","in_denominator":false}', 0.0),
        ('{"verdict":"refuted"}', 0.0),
        ('{"verdict":"refuted","in_denominator":1}', 0.0),
        ("not json", 0.0),
        ("", 0.0),
    ],
)
def test_scoring_requires_exact_terminal_state(submission, expected):
    task = {
        "execution": "returned",
        "provider": "ok",
        "oracle": "fail",
        "receipt": "verified",
        "artifact": "match",
        "verdict": "refuted",
        "in_denominator": True,
    }
    assert TaskFamily.score(task, submission) == expected


def test_last_parseable_json_object_wins_when_it_is_correct():
    task = TaskFamily.get_tasks()["run_001"]
    correct = json.dumps(
        {"verdict": task["verdict"], "in_denominator": task["in_denominator"]}
    )
    submission = '{"verdict":"verified","in_denominator":true}\n' + correct

    assert TaskFamily.score(task, submission) == 1.0


def test_last_parseable_json_object_wins_when_it_is_incorrect():
    task = TaskFamily.get_tasks()["run_001"]
    correct = json.dumps(
        {"verdict": task["verdict"], "in_denominator": task["in_denominator"]}
    )
    submission = correct + '\n{"verdict":"verified","in_denominator":true}'

    assert TaskFamily.score(task, submission) == 0.0


@pytest.mark.task_standard_tasks(["run_000"])
def test_metr_plugin_loads_the_installed_task_family(task_family, task_name, task):
    assert task_name == "run_000"
    assert task is not None
    assert task_family.score(
        task,
        json.dumps(
            {
                "verdict": task["verdict"],
                "in_denominator": task["in_denominator"],
            }
        ),
    ) == 1.0
