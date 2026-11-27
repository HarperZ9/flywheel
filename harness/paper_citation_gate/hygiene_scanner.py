# SPDX-License-Identifier: MIT
"""Pure-stdlib prose hygiene, path-leak, entity-claim, and citation scanner.

Scans technical papers and executive dossiers for em/en dashes, local Windows
or Unix workstation path leaks, false affirmative LLC/Inc/Corp entity claims,
and extracts all cited catalogue IDs deterministically.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any

HONEST_SCOPE_LIMIT = (
    "Performs deterministic regex and Unicode code-point scanning for em/en "
    "dashes, workstation path leaks, affirmative LLC/Inc claims, and "
    "catalogue ID citations in pure Python stdlib. Does not parse PDF glyphs."
)

EXPLICIT_CID_RE = re.compile(r"(?:catalogue_id|cid)\s*[:=#]?\s*(\d{4,6})\b", re.I)
BARE_CID_RE = re.compile(r"\b(6\d{4})\b")
WIN_PATH_RE = re.compile(r"(?:[A-Za-z]:\\|[A-Za-z]:/(?:dev|Us" + r"ers|wt|library|Windows)/)")
UNIX_HOME_RE = re.compile(r"(?:/Us" + r"ers/[A-Za-z0-9._-]+/|/ho" + r"me/[A-Za-z0-9._-]+/)")
ENTITY_TOKEN_RE = re.compile(r"\b(?:LLC|L\.L\.C\.|Inc\.?|Corp\.?|Corporation)(?=\W|$)")
NEGATION_PREFIX_RE = re.compile(
    r"(?:zero|no|not\s+an?|without|non-?)\s+(?:LLC\s*/\s*)?$",
    re.I,
)


@dataclass(frozen=True)
class DocumentHygieneResult:
    """Deterministic hygiene scan results for one document."""

    dash_hits: int
    local_path_leaks: tuple[str, ...]
    false_entity_hits: tuple[str, ...]
    cited_catalogue_ids: tuple[int, ...]


def is_strict_int(value: Any) -> bool:
    """Return True iff value is an int and not a bool."""
    return isinstance(value, int) and not isinstance(value, bool)


def is_strict_finite_float(value: Any) -> bool:
    """Return True iff value is a finite real int/float and not a bool."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def scan_document_hygiene(text: str) -> DocumentHygieneResult:
    """Scan markdown or plain text for dashes, path leaks, entity claims, and CIDs."""
    if not isinstance(text, str):
        return DocumentHygieneResult(0, (), (), ())
    dash_hits = text.count("\u2014") + text.count("\u2013")
    leaks = sorted(set(WIN_PATH_RE.findall(text) + UNIX_HOME_RE.findall(text)))
    false_entities: list[str] = []
    for match in ENTITY_TOKEN_RE.finditer(text):
        prefix = text[max(0, match.start() - 20) : match.start()]
        if not NEGATION_PREFIX_RE.search(prefix):
            false_entities.append(match.group(0))
    raw_cids = EXPLICIT_CID_RE.findall(text) + BARE_CID_RE.findall(text)
    cids = sorted({int(tok) for tok in raw_cids if tok.isdigit() and int(tok) > 0})
    return DocumentHygieneResult(
        dash_hits=dash_hits,
        local_path_leaks=tuple(leaks),
        false_entity_hits=tuple(false_entities),
        cited_catalogue_ids=tuple(cids),
    )


def canonical_sha256_hex(payload: Any) -> str:
    """Compute a deterministic SHA-256 hex digest over canonical JSON."""
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
