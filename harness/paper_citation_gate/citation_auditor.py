# SPDX-License-Identifier: MIT
"""Catalogue citation and receipt-verdict auditor for technical papers.

Cross-checks every extracted catalogue ID against a known live catalogue set
and verifies that every primary document receipt matches engine-receipt/1.
"""

from __future__ import annotations

from dataclasses import dataclass

from .hygiene_scanner import DocumentHygieneResult, is_strict_int

HONEST_SCOPE_LIMIT = (
    "Cross-checks extracted catalogue IDs against caller-supplied live ID "
    "sets and receipt match verdicts in pure Python stdlib. Does not open "
    "SQLite databases directly."
)


@dataclass(frozen=True)
class PaperSpec:
    """One technical paper or executive dossier input for verification."""

    doc_id: str
    primary_catalogue_id: int
    text: str


def validate_paper_specs(
    papers: list[PaperSpec],
    known_catalogue_ids: set[int] | None,
) -> list[str]:
    """Validate PaperSpec list structure and known catalogue ID types."""
    errors: list[str] = []
    if not isinstance(papers, list) or not papers:
        return ["papers: expected non-empty list of PaperSpec"]
    seen_ids: set[str] = set()
    for idx, spec in enumerate(papers):
        if not isinstance(spec, PaperSpec):
            errors.append(f"papers[{idx}]: expected PaperSpec")
            continue
        if not spec.doc_id.strip():
            errors.append(f"papers[{idx}]: empty doc_id")
        elif spec.doc_id in seen_ids:
            errors.append(f"papers[{idx}]: duplicate doc_id {spec.doc_id}")
        else:
            seen_ids.add(spec.doc_id)
        if not is_strict_int(spec.primary_catalogue_id) or spec.primary_catalogue_id <= 0:
            errors.append(
                f"papers[{idx}]({spec.doc_id}): invalid primary_catalogue_id"
            )
        if not isinstance(spec.text, str) or not spec.text.strip():
            errors.append(f"papers[{idx}]({spec.doc_id}): empty document text")
    if known_catalogue_ids is not None:
        for cid in known_catalogue_ids:
            if not is_strict_int(cid) or cid <= 0:
                errors.append(f"known_catalogue_ids: invalid ID {cid!r}")
                break
    return errors


def audit_single_paper(
    spec: PaperSpec,
    hygiene: DocumentHygieneResult,
    known_cids: set[int] | None,
    receipt_verdicts: dict[int, bool] | None,
) -> tuple[list[int], bool, list[str]]:
    """Audit one paper's hygiene, catalogue citations, and primary receipt."""
    violations: list[str] = []
    if hygiene.dash_hits > 0:
        violations.append(f"{spec.doc_id}: {hygiene.dash_hits} em/en dash hit(s)")
    if hygiene.local_path_leaks:
        violations.append(
            f"{spec.doc_id}: local path leak(s) {list(hygiene.local_path_leaks)}"
        )
    if hygiene.false_entity_hits:
        violations.append(
            f"{spec.doc_id}: false entity claim(s) {list(hygiene.false_entity_hits)}"
        )
    forged: list[int] = []
    if known_cids is not None:
        if spec.primary_catalogue_id not in known_cids:
            forged.append(spec.primary_catalogue_id)
        for cid in hygiene.cited_catalogue_ids:
            if cid not in known_cids:
                forged.append(cid)
    if forged:
        violations.append(
            f"{spec.doc_id}: forged or absent catalogue_id(s) {sorted(set(forged))}"
        )
    primary_matched = True
    if receipt_verdicts is not None:
        primary_matched = receipt_verdicts.get(spec.primary_catalogue_id) is True
        if not primary_matched:
            violations.append(
                f"{spec.doc_id}: primary receipt {spec.primary_catalogue_id} not MATCH"
            )
    return sorted(set(forged)), primary_matched, violations
