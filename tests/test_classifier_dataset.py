import json

import pytest

from harness.classifier_dataset import (
    ClassifierDatasetError,
    build_split_manifest,
    load_examples_jsonl,
    validate_example,
)
from harness.evidence_json import canonical_sha256


def request(*, decision_ref="route_1", state="Route this request.", eligible=None,
            choices=None, evidence_refs=None):
    return {
        "schema": "flywheel.decision-request/v1",
        "decision_ref": decision_ref,
        "state": state,
        "choices": choices if choices is not None else [
            {"id": "local", "description": "Use the local route."},
            {"id": "hosted", "description": "Use the hosted route."},
            {"id": "ask", "description": "Ask the operator."},
        ],
        "eligible_choice_ids": ["local", "hosted"] if eligible is None else eligible,
        "evidence_refs": ["ev_roster"] if evidence_refs is None else evidence_refs,
    }


def example(group, *, ref="route_1", family="routing", acceptable=None,
            kind="verified_outcome", state="Route this request.", req=None):
    return {
        "task_family": family,
        "source_group": group,
        "request": req if req is not None else request(decision_ref=ref, state=state),
        "acceptable_choice_ids": ["local"] if acceptable is None else acceptable,
        "label_provenance": {"kind": kind, "source_ref": f"receipt:{ref}"},
    }


def test_validate_example_reuses_decision_request_contract_and_hashes_snapshot():
    row = example("session-a")
    got = validate_example(row)

    assert got["request"] == row["request"]
    assert got["request"] is not row["request"]
    assert got["request_sha256"] == canonical_sha256(row["request"])
    assert got["label_provenance"] == {
        "kind": "verified_outcome",
        "source_ref": "receipt:route_1",
    }
    assert got["example_sha256"] == canonical_sha256({
        "acceptable_choice_ids": ["local"],
        "label_provenance": got["label_provenance"],
        "request": got["request"],
        "source_group": "session-a",
        "task_family": "routing",
    })


def test_empty_acceptable_choices_are_preserved_as_explicit_abstention():
    got = validate_example(example("session-a", acceptable=[]))

    assert got["acceptable_choice_ids"] == []
    assert got["label_state"] == "explicit_abstain"


@pytest.mark.parametrize("bad", [
    lambda: example("session-a", acceptable=["ask"]),
    lambda: {**example("session-a"), "acceptable_choice_ids": ["local", "local"]},
    lambda: {**example("session-a"), "label_provenance": {"kind": "rumor", "source_ref": "x"}},
    lambda: {**example("session-a"), "label_provenance": {"kind": ["teacher"], "source_ref": "x"}},
    lambda: {**example("session-a"), "request": {**request(), "state": ""}},
    lambda: {**example("bad group"), "source_group": "bad group"},
])
def test_validate_example_rejects_ineligible_labels_and_bad_provenance(bad):
    with pytest.raises(ClassifierDatasetError):
        validate_example(bad())


def test_split_manifest_is_group_disjoint_and_digest_bound():
    rows = [
        example("group-train", ref="route_train", state="Route training request."),
        example("group-cal", ref="route_cal", state="Route calibration request.", acceptable=[]),
        example("group-test", ref="route_test", state="Route test request.", acceptable=["hosted"]),
    ]

    manifest = build_split_manifest(rows, {
        "group-train": "train",
        "group-cal": "calibration",
        "group-test": "test",
    })

    assert manifest["counts"] == {
        "total": 3,
        "train": 1,
        "calibration": 1,
        "test": 1,
        "explicit_abstain": 1,
    }
    assert manifest["source_groups"] == {
        "train": ["group-train"],
        "calibration": ["group-cal"],
        "test": ["group-test"],
    }
    assert [row["split"] for row in manifest["examples"]] == [
        "calibration", "test", "train",
    ]
    body = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
    assert manifest["manifest_sha256"] == canonical_sha256(body)
    assert "held-out workflow evidence" in " ".join(manifest["does_not_prove"])


def test_split_manifest_rejects_same_normalized_input_renamed_across_groups():
    rows = [
        example("group-a", ref="original"),
        example("group-b", ref="renamed", req=request(
            decision_ref="renamed",
            state="  route THIS   request. ",
            evidence_refs=["ev_other"],
            choices=[
                {"id": "hosted_2", "description": "use the HOSTED route."},
                {"id": "ask_2", "description": " ask the operator. "},
                {"id": "local_2", "description": "use the local route."},
            ],
            eligible=["hosted_2", "local_2"],
        ), acceptable=["hosted_2"]),
    ]

    with pytest.raises(ClassifierDatasetError, match="duplicate normalized input"):
        build_split_manifest(rows, {"group-a": "train", "group-b": "test"})


def test_split_manifest_rejects_conflicting_labels_for_same_model_input():
    rows = [
        example("same-group", ref="first", acceptable=["local"]),
        example("same-group", ref="second", acceptable=["hosted"]),
    ]

    with pytest.raises(ClassifierDatasetError, match="duplicate normalized input"):
        build_split_manifest(rows, {"same-group": "train"})


def test_load_examples_jsonl_uses_strict_bounded_json(tmp_path):
    path = tmp_path / "examples.jsonl"
    path.write_text(
        json.dumps(example("g1", ref="a")) + "\n"
        + json.dumps(example("g2", ref="b", acceptable=[])) + "\n",
        encoding="utf-8",
    )

    loaded = load_examples_jsonl(path)
    assert [row["source_group"] for row in loaded] == ["g1", "g2"]

    dup = tmp_path / "dup.jsonl"
    dup.write_text('{"task_family":"routing","task_family":"tool"}\n', encoding="utf-8")
    with pytest.raises(ClassifierDatasetError):
        load_examples_jsonl(dup)


def test_load_examples_jsonl_reads_only_one_byte_past_limit(tmp_path, monkeypatch):
    path = tmp_path / "big.jsonl"
    path.write_text("{}\n" + ("x" * 100), encoding="utf-8")
    seen = []
    real_open = open

    def tracking_open(*args, **kwargs):
        handle = real_open(*args, **kwargs)
        original = handle.read

        def read(size=-1):
            seen.append(size)
            return original(size)

        handle.read = read
        return handle

    monkeypatch.setattr("builtins.open", tracking_open)

    with pytest.raises(ClassifierDatasetError, match="byte limit"):
        load_examples_jsonl(path, max_bytes=8)
    assert seen == [9]


@pytest.mark.parametrize("max_bytes", [0, -1, 1.2, True, "10"])
def test_load_examples_jsonl_rejects_bad_max_bytes(max_bytes, tmp_path):
    path = tmp_path / "examples.jsonl"
    path.write_text("", encoding="utf-8")

    with pytest.raises(ClassifierDatasetError, match="byte limit"):
        load_examples_jsonl(path, max_bytes=max_bytes)
