import hashlib
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

from harness.classifier_dataset import build_split_manifest, validate_example
from train.classifier_corpus import (
    CASES,
    FAMILIES,
    PER_CASE_BY_SPLIT,
    SPLITS,
    VERSION,
    generate_corpus,
    write_corpus,
)


REPO = Path(__file__).resolve().parents[1]
OPAQUE_REF = re.compile(r"ev:[0-9a-f]{16}\Z")


def _request_text(row):
    return json.dumps(row["request"], sort_keys=True).casefold()


def _semantic_text(row):
    request = row["request"]
    parts = [request["state"]]
    parts.extend(choice["description"] for choice in request["choices"])
    return "\n".join(parts).casefold()


def _file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _source_case(row):
    version, family, split, case, variant = row["label_provenance"]["source_ref"].split(".")
    assert version == VERSION
    assert variant.startswith("v")
    return family, split, case, int(variant[1:])


def test_generate_corpus_is_reproducible_and_contract_valid():
    first = generate_corpus(seed=41)
    second = generate_corpus(seed=41)

    assert first == second
    assert first["manifest"]["diagnostic_only"] is True
    assert "not production training data" in " ".join(first["manifest"]["does_not_prove"])
    manifest = build_split_manifest(first["examples"], first["splits"])
    assert first["manifest"]["dataset_manifest"]["manifest_sha256"] == manifest["manifest_sha256"]
    for row in first["examples"]:
        assert validate_example(row)["label_provenance"]["kind"] == "synthetic"


def test_default_corpus_size_matches_available_diversity_not_padding():
    corpus = generate_corpus(seed=3)
    counts = corpus["manifest"]["dataset_manifest"]["counts"]
    expected = {
        split: sum(len(CASES[family]) for family in FAMILIES) * PER_CASE_BY_SPLIT[split]
        for split in SPLITS
    }

    assert {split: counts[split] for split in SPLITS} == expected
    assert counts["total"] == sum(expected.values())
    assert counts["total"] < 200


def test_every_case_has_distinct_split_paraphrases_and_no_split_overlap():
    corpus = generate_corpus(seed=7)
    rows_by_case = defaultdict(list)
    by_family_split = Counter()

    for row in corpus["examples"]:
        family, split, case, _variant = _source_case(row)
        rows_by_case[(family, split, case)].append(row)
        by_family_split[(family, split)] += 1

    assert set(by_family_split) == {
        (family, split) for family in FAMILIES for split in SPLITS
    }
    for family in FAMILIES:
        for split in SPLITS:
            assert by_family_split[(family, split)] == len(CASES[family]) * PER_CASE_BY_SPLIT[split]
        for case in CASES[family]:
            for split in SPLITS:
                rows = rows_by_case[(family, split, case)]
                assert len(rows) == PER_CASE_BY_SPLIT[split]
                assert len({row["request"]["state"] for row in rows}) == len(rows)

    groups = corpus["manifest"]["dataset_manifest"]["source_groups"]
    assert set(groups["train"]).isdisjoint(groups["calibration"])
    assert set(groups["train"]).isdisjoint(groups["test"])
    assert set(groups["calibration"]).isdisjoint(groups["test"])


def test_request_text_has_no_fixture_or_source_metadata_leakage():
    corpus = generate_corpus(seed=13)

    for row in corpus["examples"]:
        request_text = _request_text(row)
        assert VERSION.casefold() not in request_text
        assert row["source_group"].casefold() not in request_text
        assert row["label_provenance"]["source_ref"].casefold() not in request_text
        assert "fixture" not in request_text
        assert "semantic case" not in request_text
        assert "empty label" not in request_text
        assert "v0" not in request_text
        assert all(OPAQUE_REF.fullmatch(ref) for ref in row["request"]["evidence_refs"])


def test_labels_are_eligible_abstentions_empty_and_no_named_abstain_choice():
    corpus = generate_corpus(seed=19)
    abstain_families = set()
    full_eligible = partial_eligible = 0

    for row in corpus["examples"]:
        eligible = set(row["request"]["eligible_choice_ids"])
        labels = set(row["acceptable_choice_ids"])
        assert labels <= eligible
        assert row["label_provenance"]["kind"] == "synthetic"
        assert "verified_outcome" not in json.dumps(row)
        assert all("abstain" not in choice["description"].casefold()
                   for choice in row["request"]["choices"])
        full_eligible += len(eligible) == len(row["request"]["choices"])
        partial_eligible += len(eligible) < len(row["request"]["choices"])
        if not labels:
            abstain_families.add(row["task_family"])
            text = _semantic_text(row)
            assert (
                "none of" in text
                or "no offered" in text
                or "no acceptable" in text
                or "no applicable" in text
                or "no listed" in text
                or "outside this tool contract" in text
            )

    assert abstain_families == set(FAMILIES)
    assert full_eligible > partial_eligible > 0


def test_no_call_is_a_positive_tool_choice_and_empty_tool_case_is_separate():
    corpus = generate_corpus(seed=23)
    by_ref = {row["label_provenance"]["source_ref"]: row for row in corpus["examples"]}
    cases = corpus["manifest"]["semantic_cases"]
    no_call_refs = [case["source_ref"] for case in cases
                    if case["family"] == "tool_selection" and case["case"] == "no_call"]
    none_refs = [case["source_ref"] for case in cases
                 if case["family"] == "tool_selection" and case["case"] == "none"]

    assert no_call_refs and none_refs
    assert all(by_ref[ref]["acceptable_choice_ids"] for ref in no_call_refs)
    assert all(not by_ref[ref]["acceptable_choice_ids"] for ref in none_refs)
    assert all("no tool call" in _semantic_text(by_ref[ref]) for ref in no_call_refs)


def test_required_diagnostic_phrases_and_routing_needs_are_inspectable():
    corpus = generate_corpus(seed=29)
    context_text = "\n".join(_semantic_text(row) for row in corpus["examples"]
                             if row["task_family"] == "context_relevance")
    for phrase in ["pinned evidence", "recovery note", "irrelevant span", "stale conflict", "negation"]:
        assert phrase in context_text

    tool_text = "\n".join(_semantic_text(row) for row in corpus["examples"]
                          if row["task_family"] == "tool_selection")
    for phrase in ["file read", "search", "math", "structured parse", "test run", "no tool call"]:
        assert phrase in tool_text

    routing_by_case = defaultdict(str)
    for row in corpus["examples"]:
        family, _split, case, _variant = _source_case(row)
        if family == "routing":
            routing_by_case[case] += " " + row["request"]["state"].casefold()
    assert "worktree" in routing_by_case["local"]
    assert "hosted endpoint" in routing_by_case["hosted"]
    assert "preference" in routing_by_case["ask"]
    assert "ownership" in routing_by_case["coordinate"]
    assert "receipts" in routing_by_case["none"]


def test_cli_writes_reproducible_jsonl_splits_and_manifest(tmp_path):
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    args = [
        sys.executable,
        "train/classifier_corpus.py",
        "--seed", "101",
        "--train-per-case", "3",
        "--calibration-per-case", "2",
        "--test-per-case", "2",
    ]

    subprocess.run([*args, "--out", str(out_a)], cwd=REPO, check=True)
    subprocess.run([*args, "--out", str(out_b)], cwd=REPO, check=True)
    for name in ["examples.jsonl", "splits.json", "manifest.json"]:
        assert (out_a / name).exists()
        assert _file_sha(out_a / name) == _file_sha(out_b / name)

    written = write_corpus(tmp_path / "direct", seed=101)
    manifest = json.loads((out_a / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["dataset_manifest"]["counts"]["total"] == len(written["examples"])
    assert manifest["content_digests"]["examples_jsonl_sha256"] == _file_sha(out_a / "examples.jsonl")
