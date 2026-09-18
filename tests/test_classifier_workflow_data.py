import json

from harness.classifier_dataset import validate_example
from train.classifier_workflow_data import build_corpus


def _state(row):
    return json.loads(row["request"]["state"])


def _choices(row):
    return {c["id"]: json.loads(c["description"]) for c in row["request"]["choices"]}


def _mismatches(state):
    return {
        k for k, v in state["request"].items()
        if state["form"].get(k) != v
    }


def test_build_corpus_is_deterministic_valid_and_development_only():
    a_examples, a_manifest, a_meta = build_corpus(seed=19, case_count=40)
    b_examples, b_manifest, b_meta = build_corpus(seed=19, case_count=40)

    assert (a_examples, a_manifest, a_meta) == (b_examples, b_manifest, b_meta)
    assert 40 <= a_meta["case_counts"]["train"] <= 60
    assert a_manifest["source_groups"]["test"] == []
    assert len(a_examples) <= 350
    assert {validate_example(row)["label_provenance"]["kind"] for row in a_examples} == {"synthetic"}
    assert {row["task_family"] for row in a_examples} == {"tool_selection"}
    assert all(len(row["request"]["choices"]) <= 10 for row in a_examples)
    assert all(len(row["request"]["state"]) < 900 for row in a_examples)
    assert all(not _state(row)["status"]["done"] for row in a_examples)
    assert all(_state(row)["id"].startswith("w") and not _state(row)["id"].startswith("wfcase_")
               for row in a_examples)


def test_noop_distractors_do_not_become_false_success_labels():
    examples, _, _ = build_corpus(seed=23, case_count=40)
    checked = False
    for row in examples:
        state = _state(row)
        for cid, meta in _choices(row).items():
            if meta.get("op") == "set" and state["form"].get(meta.get("field")) == meta.get("value"):
                checked = True
                assert cid not in row["acceptable_choice_ids"]
    assert checked


def test_wrong_edit_is_negative_and_recovery_state_labels_correction():
    examples, _, _ = build_corpus(seed=29, case_count=40)
    by_group = {}
    for row in examples:
        by_group.setdefault(row["source_group"], []).append(row)
    found = False
    for rows in by_group.values():
        for row in rows:
            state = _state(row)
            for cid, meta in _choices(row).items():
                field, value = meta.get("field"), meta.get("value")
                if meta.get("op") == "set" and field in state["request"] and value != state["request"][field]:
                    assert cid not in row["acceptable_choice_ids"]
                    recovery = [
                        item for item in rows
                        if _state(item)["form"].get(field) == value
                    ]
                    for item in recovery:
                        for rid, rmeta in _choices(item).items():
                            if (rmeta.get("op") == "set" and rmeta.get("field") == field
                                    and rmeta.get("value") == _state(item)["request"][field]):
                                assert rid in item["acceptable_choice_ids"]
                                found = True
                                break
                        if found:
                            break
                if found:
                    break
            if found:
                break
        if found:
            break
    assert found


def test_all_rollout_and_perturbation_steps_stay_in_one_source_group():
    examples, manifest, meta = build_corpus(seed=31, case_count=40)
    split_by_group = {}
    for split, groups in manifest["source_groups"].items():
        for group in groups:
            split_by_group[group] = split
    assert set(split_by_group.values()) == {"train", "calibration"}
    for case in meta["cases"]:
        group = case["source_group"]
        assert {row["source_group"] for row in examples if row["source_group"] == group} == {group}
        assert split_by_group[group] == case["split"]
    assert {row["source_group"] for row in examples} == {case["source_group"] for case in meta["cases"]}


def test_missing_option_state_is_explicit_abstention_only_when_unfinishable():
    examples, _, meta = build_corpus(seed=37, case_count=40)
    missing_groups = {case["source_group"] for case in meta["cases"] if case["kind"] == "missing_target"}
    rows = [row for row in examples if row["source_group"] in missing_groups]
    assert rows
    assert any(row["acceptable_choice_ids"] == [] for row in rows)
    for row in rows:
        if row["acceptable_choice_ids"]:
            continue
        state = _state(row)
        before = _mismatches(state)
        for cid in row["request"]["eligible_choice_ids"]:
            meta_choice = _choices(row)[cid]
            assert not (
                meta_choice.get("op") == "set"
                and meta_choice.get("field") in before
                and meta_choice.get("value") == state["request"].get(meta_choice.get("field"))
            )


def test_transient_failure_state_labels_retry_submit():
    examples, _, _ = build_corpus(seed=41, case_count=40)
    retry_rows = [
        row for row in examples
        if (_state(row).get("last") or {}).get("status") == "transient_failure"
    ]
    assert retry_rows
    for row in retry_rows:
        submit_ids = [
            cid for cid, meta in _choices(row).items()
            if cid in row["request"]["eligible_choice_ids"] and meta.get("op") == "submit"
        ]
        assert submit_ids
        assert set(submit_ids) <= set(row["acceptable_choice_ids"])
