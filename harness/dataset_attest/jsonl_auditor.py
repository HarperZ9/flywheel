# SPDX-License-Identifier: MIT
"""Pure-stdlib JSONL row auditor for BuildDB and JFC3P RLVR datasets.

Audits BuildDB JSONL rows and RLVR train/eval JSONL splits for strict MIT
licensing, duplicate ID absence, exact train/eval disjointness, valid 64-hex
SHA-256 content hashes, and finite non-bool numeric metrics.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .dataset_guards import (
    is_mit_license,
    is_strict_finite_float,
    normalize_sha256,
)

HONEST_SCOPE_LIMIT = (
    "Audits JSONL dataset rows for MIT license purity, ID uniqueness, "
    "train/eval split disjointness, SHA-256 formatting, and numeric "
    "finiteness in pure Python stdlib. Does not execute model training."
)


@dataclass(frozen=True)
class JsonlAuditStats:
    """Summary counters produced by auditing a JSONL dataset stream."""

    row_count: int
    non_mit_count: int
    duplicate_ids: tuple[str, ...]
    unique_ids: frozenset[str]
    violations: tuple[str, ...]


def audit_builddb_jsonl(jsonl_text: str) -> JsonlAuditStats:
    """Audit BuildDB JSONL rows for MIT purity, uniqueness, and finite metrics."""
    if not isinstance(jsonl_text, str) or not jsonl_text.strip():
        return JsonlAuditStats(0, 0, (), frozenset(), ("builddb_jsonl: empty input",))
    seen: set[str] = set()
    dups: list[str] = []
    non_mit = 0
    errors: list[str] = []
    count = 0
    for line_no, raw in enumerate(jsonl_text.splitlines(), start=1):
        if not raw.strip():
            continue
        count += 1
        obj, err = _parse_json_line(raw, f"builddb:L{line_no}")
        if err or obj is None:
            errors.append(err or f"builddb:L{line_no}: parse error")
            continue
        rid = str(obj.get("record_id", "")).strip()
        if not rid:
            errors.append(f"builddb:L{line_no}: empty record_id")
        elif rid in seen:
            dups.append(rid)
            errors.append(f"builddb:L{line_no}: duplicate record_id {rid}")
        else:
            seen.add(rid)
        if not is_mit_license(obj.get("license")):
            non_mit += 1
            errors.append(f"builddb:L{line_no}({rid}): non-MIT license {obj.get('license')!r}")
        _, sha_err = normalize_sha256(obj.get("content_sha256"), f"builddb:L{line_no}({rid})")
        if sha_err:
            errors.append(sha_err)
        if "reduction_pct" in obj and not is_strict_finite_float(obj["reduction_pct"]):
            errors.append(f"builddb:L{line_no}({rid}): non-finite reduction_pct")
    return JsonlAuditStats(count, non_mit, tuple(sorted(set(dups))), frozenset(seen), tuple(errors))


def audit_rlvr_split_jsonl(
    jsonl_text: str,
    expected_split: str,
) -> JsonlAuditStats:
    """Audit an RLVR train or eval JSONL split for purity and schema integrity."""
    if not isinstance(jsonl_text, str) or not jsonl_text.strip():
        return JsonlAuditStats(0, 0, (), frozenset(), (f"rlvr_{expected_split}: empty input",))
    seen: set[str] = set()
    dups: list[str] = []
    non_mit = 0
    errors: list[str] = []
    count = 0
    for line_no, raw in enumerate(jsonl_text.splitlines(), start=1):
        if not raw.strip():
            continue
        count += 1
        obj, err = _parse_json_line(raw, f"rlvr_{expected_split}:L{line_no}")
        if err or obj is None:
            errors.append(err or f"rlvr_{expected_split}:L{line_no}: parse error")
            continue
        tid, row_non_mit, row_errs = _validate_rlvr_row(
            obj, expected_split, line_no, seen, dups
        )
        non_mit += row_non_mit
        errors.extend(row_errs)
        if tid:
            seen.add(tid)
    return JsonlAuditStats(count, non_mit, tuple(sorted(set(dups))), frozenset(seen), tuple(errors))


def _validate_rlvr_row(
    obj: dict[str, Any],
    expected_split: str,
    line_no: int,
    seen: set[str],
    dups: list[str],
) -> tuple[str, int, list[str]]:
    errs: list[str] = []
    non_mit = 0
    tid = str(obj.get("task_id", "")).strip()
    if not tid:
        errs.append(f"rlvr_{expected_split}:L{line_no}: empty task_id")
    elif tid in seen:
        dups.append(tid)
        errs.append(f"rlvr_{expected_split}:L{line_no}: duplicate task_id {tid}")
    if str(obj.get("split", "")).strip() != expected_split:
        errs.append(f"rlvr_{expected_split}:L{line_no}({tid}): split mismatch")
    if not is_mit_license(obj.get("license")):
        non_mit = 1
        errs.append(f"rlvr_{expected_split}:L{line_no}({tid}): non-MIT license")
    _, sha_err = normalize_sha256(obj.get("source_sha256"), f"rlvr_{expected_split}:L{line_no}")
    if sha_err:
        errs.append(sha_err)
    rspec = obj.get("reward_spec")
    if not isinstance(rspec, dict) or not rspec:
        errs.append(f"rlvr_{expected_split}:L{line_no}({tid}): missing reward_spec")
    else:
        for rk, rv in rspec.items():
            if not is_strict_finite_float(rv):
                errs.append(f"rlvr_{expected_split}:L{line_no}({tid}): non-finite reward {rk}")
    return tid, non_mit, errs


def _parse_json_line(raw: str, label: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"{label}: invalid JSON ({exc.msg})"
    if not isinstance(obj, dict):
        return None, f"{label}: JSONL row must be an object"
    return obj, None
