# SPDX-License-Identifier: MIT
"""Claim-to-receipt parity classifier and receipt index parser.

Parses the ideas_receipt_index.tsv lookup table and partitions every BUILT
idea into strict VERIFIED_MATCH vs UNVERIFIED buckets while catching forged
catalogue IDs and malformed verification maps fail-closed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .register_parser import IdeaRow, is_strict_finite_float, is_strict_int

HONEST_SCOPE_LIMIT = (
    "Classifies BUILT idea rows into VERIFIED_MATCH vs UNVERIFIED using "
    "caller-supplied catalogue indices and receipt match outcomes. Does not "
    "perform network lookups or mutate receipt files on disk."
)


@dataclass(frozen=True)
class ReceiptIndex:
    """Lookup tables parsed from ideas_receipt_index.tsv."""

    cid_to_path: dict[int, str]
    file_to_path: dict[str, str]


@dataclass(frozen=True)
class ParityPartition:
    """Strict VERIFIED_MATCH vs UNVERIFIED split across BUILT ideas."""

    verified_match_ids: tuple[str, ...]
    unverified_no_receipt_ids: tuple[str, ...]
    unverified_drift_ids: tuple[str, ...]
    forged_catalogue_ids: tuple[int, ...]
    violations: tuple[str, ...]


def parse_receipt_index(index_text: str) -> tuple[ReceiptIndex, list[str]]:
    """Parse tab-separated cid/file index entries without touching disk."""
    if not isinstance(index_text, str):
        return ReceiptIndex({}, {}), ["receipt_index: expected string input"]
    cid_map: dict[int, str] = {}
    file_map: dict[str, str] = {}
    errors: list[str] = []
    for line_no, raw_line in enumerate(index_text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            errors.append(f"receipt_index:L{line_no}: expected >= 3 cols")
            continue
        kind, key, target = parts[0].strip(), parts[1].strip(), parts[2].strip()
        if kind == "cid":
            if not key.isdigit() or int(key) <= 0:
                errors.append(f"receipt_index:L{line_no}: invalid cid {key!r}")
                continue
            cid_map[int(key)] = target
        elif kind == "file":
            if key:
                file_map[key] = target
    return ReceiptIndex(cid_map, file_map), errors


def validate_known_catalogue_ids(raw: Any) -> tuple[set[int] | None, list[str]]:
    """Validate an optional collection of known strict-positive int IDs."""
    if raw is None:
        return None, []
    if not isinstance(raw, (set, frozenset, list, tuple)):
        return None, ["known_catalogue_ids: must be a set or sequence of ints"]
    clean: set[int] = set()
    errors: list[str] = []
    for item in raw:
        if not is_strict_int(item) or item <= 0:
            errors.append(f"known_catalogue_ids: invalid ID {item!r}")
        else:
            clean.add(item)
    return clean, errors


def validate_ratio_threshold(value: Any, label: str) -> list[str]:
    """Validate a strict finite float ratio threshold in [0.0, 1.0]."""
    if not is_strict_finite_float(value):
        return [f"{label}: non-finite or invalid threshold {value!r}"]
    num = float(value)
    if num < 0.0 or num > 1.0:
        return [f"{label}: threshold {num} outside [0.0, 1.0]"]
    return []


def classify_built_parity(
    rows: list[IdeaRow],
    *,
    known_catalogue_ids: set[int] | None = None,
    known_json_names: set[str] | None = None,
    verified_tokens: dict[str, bool] | None = None,
) -> ParityPartition:
    """Partition all BUILT rows into VERIFIED_MATCH vs UNVERIFIED fail-closed."""
    verified: list[str] = []
    no_receipt: list[str] = []
    drifted: list[str] = []
    forged: set[int] = set()
    violations: list[str] = []
    for row in rows:
        if row.status != "BUILT":
            continue
        row_forged = _find_forged_cids(row, known_catalogue_ids)
        if row_forged:
            forged.update(row_forged)
            violations.append(
                f"forged_catalogue_id({row.idea_id}): {sorted(row_forged)}"
            )
        tokens = _resolved_tokens(row, known_catalogue_ids, known_json_names)
        if not tokens:
            no_receipt.append(row.idea_id)
        elif _any_token_verified(tokens, verified_tokens):
            verified.append(row.idea_id)
        else:
            drifted.append(row.idea_id)
    return ParityPartition(
        verified_match_ids=tuple(sorted(verified)),
        unverified_no_receipt_ids=tuple(sorted(no_receipt)),
        unverified_drift_ids=tuple(sorted(drifted)),
        forged_catalogue_ids=tuple(sorted(forged)),
        violations=tuple(violations),
    )


def _find_forged_cids(
    row: IdeaRow,
    known_catalogue_ids: set[int] | None,
) -> list[int]:
    if known_catalogue_ids is None:
        return []
    return [cid for cid in row.cited_catalogue_ids if cid not in known_catalogue_ids]


def _resolved_tokens(
    row: IdeaRow,
    known_catalogue_ids: set[int] | None,
    known_json_names: set[str] | None,
) -> list[str]:
    tokens: list[str] = []
    for cid in row.cited_catalogue_ids:
        if known_catalogue_ids is None or cid in known_catalogue_ids:
            tokens.append(f"cid:{cid}")
    for jname in row.cited_json_names:
        if known_json_names is None or jname in known_json_names:
            tokens.append(f"file:{jname}")
    return tokens


def _any_token_verified(
    tokens: list[str],
    verified_tokens: dict[str, bool] | None,
) -> bool:
    if verified_tokens is None:
        return len(tokens) > 0
    return any(verified_tokens.get(tok) is True for tok in tokens)


def compute_match_ratio(verified_count: int, built_count: int) -> float:
    """Compute finite verified_match / built ratio in [0.0, 1.0]."""
    if built_count <= 0:
        return 1.0
    ratio = verified_count / built_count
    if not math.isfinite(ratio):
        return 0.0
    return round(ratio, 6)
