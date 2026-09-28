"""Dataset validation for advisory classifier experiments.

This module prepares training/evaluation records only. It does not train a
model, execute a route, authorize a tool, or certify an output.
"""
from __future__ import annotations

from pathlib import Path

from .decision_contract import ID_PATTERN, DecisionContractError, validate_request
from .evidence_json import canonical_sha256, strict_load_json

SCHEMA = "flywheel.classifier-example/v1"
MANIFEST_SCHEMA = "flywheel.classifier-split-manifest/v1"
MAX_RECORD_BYTES = 131_072
MAX_DATASET_BYTES = 16_777_216
VALID_LABEL_KINDS = {"synthetic", "human_reviewed", "verified_outcome", "teacher"}
VALID_SPLITS = ("train", "calibration", "test")
DOES_NOT_PROVE = [
    "dataset validation, label truth, model quality, or held-out workflow evidence",
    "authorization, execution safety, result correctness, or calibration",
    "competitive performance or a completed powerful classifier model",
]


class ClassifierDatasetError(ValueError):
    """Classifier dataset records fail closed."""


def _fail(message: str) -> None:
    raise ClassifierDatasetError(message)


def _id(value: object, field: str) -> str:
    if type(value) is not str or ID_PATTERN.fullmatch(value) is None:
        _fail(f"invalid {field}")
    return value


def _source_ref(value: object) -> str:
    if type(value) is not str or not value or len(value) > 512:
        _fail("invalid label source")
    if any(ord(ch) < 32 for ch in value):
        _fail("invalid label source")
    return value


def _provenance(value: object) -> dict:
    if type(value) is not dict or set(value) != {"kind", "source_ref"}:
        _fail("invalid label provenance")
    kind = value["kind"]
    if type(kind) is not str or kind not in VALID_LABEL_KINDS:
        _fail("invalid label provenance")
    return {"kind": kind, "source_ref": _source_ref(value["source_ref"])}


def _acceptable(value: object, eligible: set[str]) -> list[str]:
    if type(value) is not list:
        _fail("invalid acceptable choices")
    out, seen = [], set()
    for item in value:
        choice = _id(item, "acceptable choice")
        if choice in seen or choice not in eligible:
            _fail("invalid acceptable choices")
        seen.add(choice)
        out.append(choice)
    return out


def _base_example(record: dict, request: dict, acceptable: list[str],
                  provenance: dict) -> dict:
    return {
        "task_family": record["task_family"],
        "source_group": record["source_group"],
        "request": request,
        "acceptable_choice_ids": acceptable,
        "label_provenance": provenance,
    }


def _norm_text(value: str) -> str:
    """Model-input identity uses casefolded whitespace-normalized text."""
    return " ".join(value.casefold().split())


def _normalized_input(task_family: str, request: dict) -> dict:
    by_id = {choice["id"]: _norm_text(choice["description"])
             for choice in request["choices"]}
    return {
        "task_family": task_family.casefold(),
        "state": _norm_text(request["state"]),
        "candidate_descriptions": sorted(by_id.values()),
        "eligible_candidate_descriptions": sorted(
            by_id[choice_id] for choice_id in request["eligible_choice_ids"]),
    }


def validate_example(record: dict) -> dict:
    """Validate one classifier example and attach reproducible digests."""
    keys = {
        "task_family", "source_group", "request",
        "acceptable_choice_ids", "label_provenance",
    }
    if type(record) is not dict or set(record) != keys:
        _fail("invalid classifier example")
    task_family = _id(record["task_family"], "task family")
    source_group = _id(record["source_group"], "source group")
    try:
        request = validate_request(record["request"])
    except DecisionContractError as exc:
        raise ClassifierDatasetError("invalid decision request") from exc
    eligible = set(request["eligible_choice_ids"])
    acceptable = _acceptable(record["acceptable_choice_ids"], eligible)
    provenance = _provenance(record["label_provenance"])
    base = _base_example(
        {"task_family": task_family, "source_group": source_group},
        request, acceptable, provenance)
    normalized = _normalized_input(task_family, request)
    return {
        **base,
        "schema": SCHEMA,
        "request_sha256": canonical_sha256(request),
        "normalized_input_sha256": canonical_sha256(normalized),
        "example_sha256": canonical_sha256(base),
        "label_state": "explicit_abstain" if not acceptable else "choice_label",
    }


def load_examples_jsonl(path: str | Path, *,
                        max_bytes: int = MAX_DATASET_BYTES) -> list[dict]:
    """Load bounded JSONL examples using Flywheel's strict JSON parser."""
    if type(max_bytes) is not int or max_bytes <= 0 or max_bytes > MAX_DATASET_BYTES:
        _fail("dataset byte limit is invalid")
    try:
        with open(Path(path), "rb") as handle:
            raw = handle.read(max_bytes + 1)
    except OSError as exc:
        raise ClassifierDatasetError("dataset unreadable") from exc
    if len(raw) > max_bytes:
        _fail("dataset exceeds byte limit")
    rows = []
    for line_no, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = strict_load_json(
                line, max_bytes=MAX_RECORD_BYTES, max_depth=12)
            rows.append(validate_example(value))
        except (ValueError, RecursionError) as exc:
            raise ClassifierDatasetError(
                f"invalid classifier example at line {line_no}") from exc
    return rows


def _split_of(group: str, split_by_group: dict[str, str]) -> str:
    split = split_by_group.get(group)
    if split not in VALID_SPLITS:
        _fail("invalid or missing split assignment")
    return split


def build_split_manifest(records: list[dict], split_by_group: dict[str, str]) -> dict:
    """Build a deterministic group-disjoint split manifest.

    Duplicate normalized inputs across different source groups are rejected: a
    renamed session/project group must not leak the same record into held-out data.
    """
    if type(records) is not list or type(split_by_group) is not dict:
        _fail("invalid split manifest input")
    examples = [validate_example(row) for row in records]
    seen_inputs: set[str] = set()
    manifest_rows = []
    source_groups = {name: set() for name in VALID_SPLITS}
    counts = {"total": len(examples), "train": 0, "calibration": 0,
              "test": 0, "explicit_abstain": 0}
    for item in examples:
        group = item["source_group"]
        split = _split_of(group, split_by_group)
        normalized_hash = item["normalized_input_sha256"]
        if normalized_hash in seen_inputs:
            _fail("duplicate normalized input across source groups")
        seen_inputs.add(normalized_hash)
        counts[split] += 1
        counts["explicit_abstain"] += int(item["label_state"] == "explicit_abstain")
        source_groups[split].add(group)
        manifest_rows.append({
            "split": split,
            "task_family": item["task_family"],
            "source_group": group,
            "example_sha256": item["example_sha256"],
            "request_sha256": item["request_sha256"],
            "normalized_input_sha256": item["normalized_input_sha256"],
            "acceptable_choice_ids": list(item["acceptable_choice_ids"]),
            "label_kind": item["label_provenance"]["kind"],
            "label_source_ref": item["label_provenance"]["source_ref"],
        })
    manifest_rows.sort(
        key=lambda row: (row["split"], row["source_group"], row["example_sha256"]))
    body = {
        "schema": MANIFEST_SCHEMA,
        "split_policy": "explicit-source-group/v1",
        "counts": counts,
        "source_groups": {
            name: sorted(source_groups[name]) for name in VALID_SPLITS
        },
        "examples": manifest_rows,
        "input_sha256": canonical_sha256([row["example_sha256"]
                                          for row in manifest_rows]),
        "does_not_prove": DOES_NOT_PROVE,
    }
    return {**body, "manifest_sha256": canonical_sha256(body)}
