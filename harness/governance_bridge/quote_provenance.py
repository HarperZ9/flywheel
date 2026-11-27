# SPDX-License-Identifier: MIT
"""Standing-rule verbatim quotation provenance linter (N34 / SIG-098, stdlib only).

Verifies that every standing-rule citation carries a valid ISO-8601 date,
the exact FIPS 180-4 SHA-256 digest of the canonical ruling text, and an
exact verbatim substring of at least 8 characters. Paraphrased, misdated,
short, or hash-tampered citations fail closed with deterministic bitmasks.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

HONEST_SCOPE_LIMIT = (
    "Checks deterministic ISO-8601 date validity, SHA-256 source-hash equality, "
    "and exact verbatim substring match against supplied canonical rulings; it "
    "does not verify external legal authority or unrecorded verbal approvals."
)

BIT_INVALID_DATE = 1
BIT_HASH_MISMATCH = 2
BIT_NON_VERBATIM = 4
BIT_SHORT_QUOTE = 8
MIN_QUOTE_CHARS = 8

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RULE_LINE_RE = re.compile(r"^\s*[-*]\s+\*\*(?P<rule_id>[A-Za-z0-9_.-]+)\*\*\s*:\s*(?P<body>.+)$")
_QUOTED_RULE_RE = re.compile(
    r'\((?P<date>\d{4}-\d{2}-\d{2}),\s*(?P<digest>sha256:[0-9a-f]{64})\)\s*:\s*"(?P<quote>[^"]+)"'
)


def sha256_text(text: str) -> str:
    """Return prefixed FIPS 180-4 SHA-256 hex digest of UTF-8 text."""
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_valid_iso_date(value: str) -> bool:
    """Return True iff `value` is a strict YYYY-MM-DD calendar date."""
    if not isinstance(value, str) or not _ISO_DATE_RE.match(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


@dataclass(frozen=True)
class StandingRule:
    rule_id: str
    canonical_text: str
    dated_iso: str

    @property
    def source_sha256(self) -> str:
        return sha256_text(self.canonical_text)


@dataclass(frozen=True)
class RuleCitation:
    rule_id: str
    date_iso: str
    cited_sha256: str
    quote: str


@dataclass(frozen=True)
class CitationLintResult:
    rule_id: str
    ok: bool
    mask: int
    violations: tuple[str, ...]


def lint_citation(rule: StandingRule, citation: RuleCitation) -> CitationLintResult:
    """Lint one citation against its canonical standing rule fail-closed."""
    mask = 0
    violations: list[str] = []

    if not is_valid_iso_date(citation.date_iso):
        mask |= BIT_INVALID_DATE
        violations.append("INVALID_OR_MISSING_DATE")
    elif is_valid_iso_date(rule.dated_iso) and citation.date_iso != rule.dated_iso:
        mask |= BIT_INVALID_DATE
        violations.append("DATE_MISMATCH")

    if citation.cited_sha256 != rule.source_sha256:
        mask |= BIT_HASH_MISMATCH
        violations.append("SOURCE_HASH_MISMATCH")

    if len(citation.quote) < MIN_QUOTE_CHARS:
        mask |= BIT_SHORT_QUOTE
        violations.append("EMPTY_OR_SHORT_QUOTE")
    elif citation.quote not in rule.canonical_text:
        mask |= BIT_NON_VERBATIM
        violations.append("PARAPHRASED_OR_NON_VERBATIM")

    return CitationLintResult(
        rule_id=rule.rule_id,
        ok=(mask == 0),
        mask=mask,
        violations=tuple(violations),
    )


def lint_citations(
    rules: Mapping[str, StandingRule],
    citations: Sequence[RuleCitation],
) -> dict[str, object]:
    """Verify a batch of citations against a canonical rule registry."""
    results: list[dict[str, object]] = []
    failed = 0
    for cit in citations:
        rule = rules.get(cit.rule_id)
        if rule is None:
            failed += 1
            results.append({
                "rule_id": cit.rule_id,
                "ok": False,
                "mask": BIT_HASH_MISMATCH,
                "violations": ["UNKNOWN_RULE_ID"],
            })
            continue
        res = lint_citation(rule, cit)
        if not res.ok:
            failed += 1
        results.append({
            "rule_id": res.rule_id,
            "ok": res.ok,
            "mask": res.mask,
            "violations": list(res.violations),
        })
    return {
        "ok": failed == 0,
        "checked": len(results),
        "failed": failed,
        "results": results,
        "honest_scope_limit": HONEST_SCOPE_LIMIT,
    }


def lint_instruction_document(
    document_text: str,
    rules: Mapping[str, StandingRule],
) -> dict[str, object]:
    """Scan standing-rule bullets in an instruction file and flag unquoted or invalid rules."""
    findings: list[dict[str, object]] = []
    rules_checked = 0
    for lineno, line in enumerate(document_text.splitlines(), start=1):
        rm = _RULE_LINE_RE.match(line)
        if not rm:
            continue
        rules_checked += 1
        rid = rm.group("rule_id")
        body = rm.group("body")
        qm = _QUOTED_RULE_RE.search(body)
        if not qm:
            findings.append({
                "line": lineno,
                "rule_id": rid,
                "mask": BIT_INVALID_DATE | BIT_HASH_MISMATCH | BIT_SHORT_QUOTE,
                "violations": ["MISSING_DATED_VERBATIM_QUOTE"],
            })
            continue
        rule = rules.get(rid)
        if rule is None:
            findings.append({
                "line": lineno,
                "rule_id": rid,
                "mask": BIT_HASH_MISMATCH,
                "violations": ["UNKNOWN_RULE_ID"],
            })
            continue
        res = lint_citation(
            rule,
            RuleCitation(rid, qm.group("date"), qm.group("digest"), qm.group("quote")),
        )
        if not res.ok:
            findings.append({
                "line": lineno,
                "rule_id": rid,
                "mask": res.mask,
                "violations": list(res.violations),
            })
    return {
        "ok": len(findings) == 0 and rules_checked > 0,
        "rules_checked": rules_checked,
        "findings": findings,
        "honest_scope_limit": HONEST_SCOPE_LIMIT,
    }
