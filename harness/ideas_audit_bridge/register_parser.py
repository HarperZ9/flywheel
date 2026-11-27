# SPDX-License-Identifier: MIT
"""Pure-stdlib parser for the 18-column AUTHOR_IDEAS_REGISTER.tsv schema.

Validates exact 18-column layout, unique idea IDs, legal status values, strict
integer score ranges (1..10, rejecting NaN/Inf/bool), zero FLAG cells, and
deterministic extraction of cited catalogue IDs and receipt JSON basenames.
"""

from __future__ import annotations

import csv
import io
import math
import re
from dataclasses import dataclass
from typing import Any

HONEST_SCOPE_LIMIT = (
    "Parses and validates the 18-column ideas register schema, score bounds, "
    "and citation tokens in pure stdlib Python. Does not execute external "
    "receipt verifiers or mutate source registers."
)

REQUIRED_IDEAS_COLUMNS: tuple[str, ...] = (
    "idea_id",
    "domain",
    "subdomain",
    "title",
    "first_seen",
    "last_seen",
    "session_provenance",
    "mentions_or_freq",
    "status_2026_11_25",
    "flagship_home",
    "existing_upstream_artifacts",
    "next_buildlang_or_engine_step",
    "first_failing_test",
    "strategic_priority",
    "entry_kind",
    "value_score",
    "feasibility_score",
    "origin_repo",
)

LEGAL_STATUSES: frozenset[str] = frozenset({"BUILT", "PARTIAL", "UNBUILT"})

EXPLICIT_CID_RE = re.compile(r"(?:catalogue_id|cid)\s*[:=#]?\s*(\d{4,6})\b", re.I)
BARE_CID_RE = re.compile(r"\b(6\d{4})\b")
JSON_NAME_RE = re.compile(r"([A-Za-z0-9_.\-]+\.json)\b")


@dataclass(frozen=True)
class IdeaRow:
    """One validated row from the 18-column ideas register."""

    idea_id: str
    status: str
    flagship_home: str
    value_score: int
    feasibility_score: int
    cited_catalogue_ids: tuple[int, ...]
    cited_json_names: tuple[str, ...]


def is_strict_int(value: Any) -> bool:
    """Return True iff value is an int and not a bool."""
    return isinstance(value, int) and not isinstance(value, bool)


def is_strict_finite_float(value: Any) -> bool:
    """Return True iff value is a finite real int/float (never bool)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def parse_score_1_to_10(raw: Any, label: str) -> tuple[int | None, str | None]:
    """Parse a strict integer score in [1, 10], rejecting bool/NaN/Inf."""
    if isinstance(raw, bool):
        return None, f"{label}: boolean score rejected"
    if isinstance(raw, int):
        return (raw, None) if 1 <= raw <= 10 else (None, f"{label}: out of 1..10")
    if isinstance(raw, float):
        if not math.isfinite(raw) or not raw.is_integer():
            return None, f"{label}: non-integer or non-finite float {raw!r}"
        ival = int(raw)
        return (ival, None) if 1 <= ival <= 10 else (None, f"{label}: out of 1..10")
    if isinstance(raw, str):
        text = raw.strip()
        if text.isdigit():
            ival = int(text)
            if 1 <= ival <= 10:
                return ival, None
        return None, f"{label}: invalid score {raw!r}"
    return None, f"{label}: unsupported score type {type(raw).__name__}"


def extract_citations(evidence: str) -> tuple[tuple[int, ...], tuple[str, ...]]:
    """Extract sorted unique catalogue IDs and receipt JSON basenames."""
    raw_cids = EXPLICIT_CID_RE.findall(evidence) + BARE_CID_RE.findall(evidence)
    cids = sorted({int(tok) for tok in raw_cids if tok.isdigit() and int(tok) > 0})
    json_names = sorted(set(JSON_NAME_RE.findall(evidence)))
    return tuple(cids), tuple(json_names)


def parse_ideas_register(tsv_text: str) -> tuple[list[IdeaRow], list[str]]:
    """Parse and validate 18-column AUTHOR_IDEAS_REGISTER.tsv text."""
    if not isinstance(tsv_text, str) or not tsv_text.strip():
        return [], ["ideas_tsv: empty or non-string input"]
    reader = csv.reader(io.StringIO(tsv_text), delimiter="\t")
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    if not rows:
        return [], ["ideas_tsv: missing header row"]
    header = tuple(col.strip() for col in rows[0])
    if header != REQUIRED_IDEAS_COLUMNS:
        return [], [f"ideas_tsv: expected 18-col schema, got {len(header)} cols"]
    return _parse_ideas_body(rows[1:])


def _parse_ideas_body(body: list[list[str]]) -> tuple[list[IdeaRow], list[str]]:
    parsed: list[IdeaRow] = []
    errors: list[str] = []
    seen: set[str] = set()
    for line_no, cols in enumerate(body, start=2):
        row, row_errs = _parse_one_idea_row(cols, line_no, seen)
        errors.extend(row_errs)
        if row is not None:
            parsed.append(row)
    return parsed, errors


def _parse_one_idea_row(
    cols: list[str],
    line_no: int,
    seen: set[str],
) -> tuple[IdeaRow | None, list[str]]:
    if len(cols) != len(REQUIRED_IDEAS_COLUMNS):
        return None, [f"ideas_tsv:L{line_no}: expected 18 cols, got {len(cols)}"]
    errs: list[str] = []
    if any(cell.strip() == "FLAG" for cell in cols):
        errs.append(f"ideas_tsv:L{line_no}: forbidden FLAG cell present")
    iid = cols[0].strip()
    if not iid:
        errs.append(f"ideas_tsv:L{line_no}: empty idea_id")
    elif iid in seen:
        errs.append(f"ideas_tsv:L{line_no}: duplicate idea_id {iid}")
    else:
        seen.add(iid)
    status = cols[8].strip()
    if status not in LEGAL_STATUSES:
        errs.append(f"ideas_tsv:L{line_no}({iid}): illegal status {status!r}")
    val_score, val_err = parse_score_1_to_10(cols[15], f"L{line_no}({iid}).value")
    feas_score, feas_err = parse_score_1_to_10(
        cols[16], f"L{line_no}({iid}).feasibility"
    )
    if val_err:
        errs.append(val_err)
    if feas_err:
        errs.append(feas_err)
    if errs or val_score is None or feas_score is None:
        return None, errs
    cids, jsons = extract_citations(cols[10])
    return IdeaRow(iid, status, cols[9].strip(), val_score, feas_score, cids, jsons), []
