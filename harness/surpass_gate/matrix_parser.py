# SPDX-License-Identifier: MIT
"""Pure-stdlib parser for Competitive Surpass Matrix TSV and JSON artifacts.

Parses the 8-column COMMONS_COMPETITIVE_SIGNALS.tsv registry and the matching
competitive surpass matrix JSON payload, validating column layout, signal ID
uniqueness, tier vocabulary, and strict numeric bounds.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import Any

from .numeric_guards import (
    is_strict_int,
    validate_catalogue_id_list,
    validate_percentage,
)

HONEST_SCOPE_LIMIT = (
    "Validates structural schema, ID completeness, tier vocabulary, and "
    "numeric finiteness of TSV and JSON surpass registries in memory. Does "
    "not re-run underlying benchmark binaries or compiler proofs."
)

REQUIRED_TSV_COLUMNS: tuple[str, ...] = (
    "signal_id",
    "lane",
    "competitor_or_topic",
    "community_opinion_or_pain_point",
    "contextualized_why",
    "surpass_target",
    "linked_idea_id",
    "linked_flagship",
)

LEGAL_TIERS: frozenset[str] = frozenset(
    {
        "surpassed_with_receipt",
        "parity_verified",
        "open_next_wave_opportunity",
    }
)


@dataclass(frozen=True)
class SignalTsvRecord:
    """One validated row from COMMONS_COMPETITIVE_SIGNALS.tsv."""

    signal_id: str
    lane: str
    linked_idea_id: str
    linked_flagship: str


@dataclass(frozen=True)
class MatrixSignalRecord:
    """One validated signal entry from the surpass matrix JSON."""

    signal_id: str
    lane: str
    tier: str
    evidence_catalogue_ids: tuple[int, ...]


def parse_signals_tsv(tsv_text: str) -> tuple[list[SignalTsvRecord], list[str]]:
    """Parse and validate COMMONS_COMPETITIVE_SIGNALS.tsv text."""
    if not isinstance(tsv_text, str) or not tsv_text.strip():
        return [], ["signals_tsv: empty or non-string input"]
    reader = csv.reader(io.StringIO(tsv_text), delimiter="\t")
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    if not rows:
        return [], ["signals_tsv: missing header row"]
    header = tuple(col.strip() for col in rows[0])
    if header != REQUIRED_TSV_COLUMNS:
        return [], [f"signals_tsv: header mismatch {header!r}"]
    return _parse_tsv_body(rows[1:])


def _parse_tsv_body(
    body: list[list[str]],
) -> tuple[list[SignalTsvRecord], list[str]]:
    records: list[SignalTsvRecord] = []
    errors: list[str] = []
    seen: set[str] = set()
    for line_no, cols in enumerate(body, start=2):
        if len(cols) != len(REQUIRED_TSV_COLUMNS):
            errors.append(f"signals_tsv:L{line_no}: expected 8 cols, got {len(cols)}")
            continue
        sid = cols[0].strip()
        if not sid:
            errors.append(f"signals_tsv:L{line_no}: empty signal_id")
            continue
        if sid in seen:
            errors.append(f"signals_tsv:L{line_no}: duplicate signal_id {sid}")
            continue
        seen.add(sid)
        records.append(
            SignalTsvRecord(
                signal_id=sid,
                lane=cols[1].strip(),
                linked_idea_id=cols[6].strip(),
                linked_flagship=cols[7].strip(),
            )
        )
    return records, errors


def parse_matrix_signals(
    matrix_obj: Any,
) -> tuple[list[MatrixSignalRecord], list[str]]:
    """Parse and validate the signals array inside the surpass matrix JSON."""
    if not isinstance(matrix_obj, dict):
        return [], ["matrix_json: root must be a JSON object"]
    raw_signals = matrix_obj.get("signals")
    if not isinstance(raw_signals, list) or not raw_signals:
        return [], ["matrix_json: missing non-empty 'signals' list"]
    records: list[MatrixSignalRecord] = []
    errors: list[str] = []
    seen: set[str] = set()
    for idx, item in enumerate(raw_signals):
        rec, item_errs = _parse_one_signal(item, idx, seen)
        errors.extend(item_errs)
        if rec is not None:
            records.append(rec)
    return records, errors


def _parse_one_signal(
    item: Any,
    idx: int,
    seen: set[str],
) -> tuple[MatrixSignalRecord | None, list[str]]:
    if not isinstance(item, dict):
        return None, [f"signals[{idx}]: entry must be an object"]
    sid = str(item.get("signal_id", "")).strip()
    lane = str(item.get("lane", "")).strip()
    tier = str(item.get("tier", "")).strip()
    errs: list[str] = []
    if not sid:
        errs.append(f"signals[{idx}]: empty signal_id")
    elif sid in seen:
        errs.append(f"signals[{idx}]: duplicate signal_id {sid}")
    else:
        seen.add(sid)
    if tier not in LEGAL_TIERS:
        errs.append(f"signals[{idx}]({sid}): illegal tier {tier!r}")
    cids, cid_errs = validate_catalogue_id_list(
        item.get("evidence_catalogue_ids"),
        f"signals[{idx}]({sid}).evidence_catalogue_ids",
    )
    errs.extend(cid_errs)
    if errs:
        return None, errs
    return MatrixSignalRecord(sid, lane, tier, tuple(sorted(set(cids)))), []


def validate_summary_block(
    matrix_obj: dict[str, Any],
    records: list[MatrixSignalRecord],
) -> list[str]:
    """Verify summary counts and percentages match parsed signals exactly."""
    summary = matrix_obj.get("summary")
    if not isinstance(summary, dict):
        return ["matrix_json: missing 'summary' object"]
    counts = _count_tiers(records)
    errors = _check_summary_counts(summary, counts)
    errors.extend(_check_summary_percentages(summary, counts))
    return errors


def _count_tiers(records: list[MatrixSignalRecord]) -> dict[str, int]:
    total = len(records)
    surpassed = sum(1 for r in records if r.tier == "surpassed_with_receipt")
    parity = sum(1 for r in records if r.tier == "parity_verified")
    open_cnt = sum(1 for r in records if r.tier == "open_next_wave_opportunity")
    return {
        "total_signals": total,
        "surpassed_with_receipt": surpassed,
        "parity_verified": parity,
        "open_next_wave_opportunity": open_cnt,
        "combined_covered": surpassed + parity,
    }


def _check_summary_counts(
    summary: dict[str, Any],
    expected: dict[str, int],
) -> list[str]:
    errors: list[str] = []
    for key, exp_val in expected.items():
        got = summary.get(key)
        if not is_strict_int(got):
            errors.append(f"summary.{key}: expected strict int, got {got!r}")
        elif got != exp_val:
            errors.append(f"summary.{key}: reported {got} != actual {exp_val}")
    return errors


def _check_summary_percentages(
    summary: dict[str, Any],
    expected: dict[str, int],
) -> list[str]:
    total = expected["total_signals"]
    if total <= 0:
        return ["summary: total_signals must be positive"]
    pairs = (
        ("surpassed_pct", expected["surpassed_with_receipt"]),
        ("parity_pct", expected["parity_verified"]),
        ("combined_covered_pct", expected["combined_covered"]),
        ("open_pct", expected["open_next_wave_opportunity"]),
    )
    errors: list[str] = []
    for pct_key, count in pairs:
        if pct_key not in summary:
            continue
        raw_pct = summary[pct_key]
        pct_errs = validate_percentage(raw_pct, f"summary.{pct_key}")
        if pct_errs:
            errors.extend(pct_errs)
            continue
        actual_pct = (100.0 * count) / total
        if abs(float(raw_pct) - actual_pct) > 0.05:
            errors.append(
                f"summary.{pct_key}: reported {raw_pct} != actual {actual_pct:.2f}"
            )
    return errors
