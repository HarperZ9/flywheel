# SPDX-License-Identifier: MIT
"""Fail-closed Flywheel oracle for Technical Papers and Executive Dossiers.

Verifies the 3-Paper Technical Trilogy and Enterprise Dossier against live
catalogue IDs and engine-receipt/1 MATCH verdicts while rejecting forged
catalogue IDs, local path leaks, em/en dashes, and false LLC/Inc claims.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .citation_auditor import PaperSpec, audit_single_paper, validate_paper_specs
from .hygiene_scanner import (
    canonical_sha256_hex,
    is_strict_finite_float,
    is_strict_int,
    scan_document_hygiene,
)

HONEST_SCOPE_LIMIT = (
    "Verifies markdown technical papers and dossiers for catalogue ID "
    "provenance, receipt MATCH verdicts, zero local path leaks, zero em/en "
    "dashes, and zero affirmative LLC/Inc claims in pure Python stdlib. "
    "Does not inspect rendered PDF layout."
)


@dataclass(frozen=True)
class PaperCitationReport:
    """Fail-closed attestation verdict for papers and executive dossiers."""

    passed: bool
    docs_checked: int
    unique_catalogue_ids_cited: int
    forged_catalogue_ids: tuple[int, ...]
    local_path_leaks: int
    dash_hits: int
    false_entity_hits: int
    primary_receipts_matched: int
    paper_citation_attestation_sha256: str
    violations: tuple[str, ...]
    honest_scope_limit: str = HONEST_SCOPE_LIMIT


def _validate_policy(min_docs: int, min_match_ratio: float) -> list[str]:
    errors: list[str] = []
    if not is_strict_int(min_docs) or min_docs <= 0:
        errors.append(f"min_docs: expected positive strict int, got {min_docs!r}")
    if not is_strict_finite_float(min_match_ratio):
        errors.append(f"min_match_ratio: non-finite or invalid {min_match_ratio!r}")
    elif not (0.0 <= float(min_match_ratio) <= 1.0):
        errors.append(f"min_match_ratio: {min_match_ratio} outside [0.0, 1.0]")
    return errors


def verify_paper_bundle(
    papers: list[PaperSpec],
    *,
    known_catalogue_ids: set[int] | None = None,
    receipt_verdicts: dict[int, bool] | None = None,
    min_docs: int = 1,
    min_match_ratio: float = 1.0,
) -> PaperCitationReport:
    """Run fail-closed citation and hygiene verification across a paper bundle."""
    pre_errs = _validate_policy(min_docs, min_match_ratio) + validate_paper_specs(
        papers, known_catalogue_ids
    )
    if pre_errs:
        return _fail_report("; ".join(pre_errs))
    all_cids: set[int] = set()
    all_forged: set[int] = set()
    totals = [0, 0, 0, 0]  # leaks, dashes, entities, matched_primary
    violations: list[str] = []
    doc_digests: list[dict[str, object]] = []
    for spec in sorted(papers, key=lambda p: p.doc_id):
        hyg = scan_document_hygiene(spec.text)
        forged, p_ok, errs = audit_single_paper(
            spec, hyg, known_catalogue_ids, receipt_verdicts
        )
        all_cids.update(hyg.cited_catalogue_ids)
        all_cids.add(spec.primary_catalogue_id)
        all_forged.update(forged)
        totals[0] += len(hyg.local_path_leaks)
        totals[1] += hyg.dash_hits
        totals[2] += len(hyg.false_entity_hits)
        totals[3] += 1 if p_ok else 0
        violations.extend(errs)
        doc_digests.append({
            "doc_id": spec.doc_id,
            "primary_catalogue_id": spec.primary_catalogue_id,
            "sha256": hashlib.sha256(spec.text.encode("utf-8")).hexdigest(),
            "cited_count": len(hyg.cited_catalogue_ids),
        })
    return _finalize_bundle(
        len(papers), min_docs, float(min_match_ratio), all_cids, all_forged,
        totals[0], totals[1], totals[2], totals[3], doc_digests, violations,
    )


def _finalize_bundle(
    doc_count: int,
    min_docs: int,
    min_match_ratio: float,
    all_cids: set[int],
    all_forged: set[int],
    leaks: int,
    dashes: int,
    entities: int,
    matched_primary: int,
    doc_digests: list[dict[str, object]],
    violations: list[str],
) -> PaperCitationReport:
    if doc_count < min_docs:
        violations.append(f"docs_checked {doc_count} < min_docs {min_docs}")
    ratio = matched_primary / doc_count if doc_count > 0 else 0.0
    if ratio < min_match_ratio:
        violations.append(f"primary_match_ratio {ratio:.4f} < {min_match_ratio:.4f}")
    attest = {
        "docs": doc_digests,
        "unique_catalogue_ids_cited": len(all_cids),
        "forged_catalogue_ids": sorted(all_forged),
        "local_path_leaks": leaks,
        "dash_hits": dashes,
        "false_entity_hits": entities,
        "primary_receipts_matched": matched_primary,
    }
    return PaperCitationReport(
        passed=len(violations) == 0,
        docs_checked=doc_count,
        unique_catalogue_ids_cited=len(all_cids),
        forged_catalogue_ids=tuple(sorted(all_forged)),
        local_path_leaks=leaks,
        dash_hits=dashes,
        false_entity_hits=entities,
        primary_receipts_matched=matched_primary,
        paper_citation_attestation_sha256=canonical_sha256_hex(attest),
        violations=tuple(violations),
    )


def _fail_report(message: str) -> PaperCitationReport:
    return PaperCitationReport(False, 0, 0, (), 0, 0, 0, 0, "", (message,))


def verify_paper_bundle_files(
    doc_entries: list[tuple[str, int, Path | str]],
    *,
    known_catalogue_ids: set[int] | None = None,
    receipt_verdicts: dict[int, bool] | None = None,
    min_docs: int = 1,
    min_match_ratio: float = 1.0,
) -> PaperCitationReport:
    """Load markdown files from disk and verify fail-closed."""
    specs: list[PaperSpec] = []
    for doc_id, cid, fpath in doc_entries:
        try:
            text = Path(fpath).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return _fail_report(f"io_error({doc_id}): {exc}")
        specs.append(PaperSpec(doc_id=doc_id, primary_catalogue_id=cid, text=text))
    return verify_paper_bundle(
        specs,
        known_catalogue_ids=known_catalogue_ids,
        receipt_verdicts=receipt_verdicts,
        min_docs=min_docs,
        min_match_ratio=min_match_ratio,
    )
