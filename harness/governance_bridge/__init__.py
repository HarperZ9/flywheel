# SPDX-License-Identifier: MIT
"""Pure-stdlib governance bridge package (`N34`, `N68`, `N70`)."""

from __future__ import annotations

from .anti_softness import (
    DIRECT_FALSIFICATION_MARKERS,
    HEDGING_PHRASES,
    HONEST_SCOPE_LIMIT as ANTI_SOFTNESS_LIMIT,
    SYCOPHANCY_PHRASES,
    TIDY_REDEMPTION_PHRASES,
    CriticScore,
    audit_dialogue_turns,
    evaluate_transcript,
)
from .boring_bridge import (
    BUNDLE_SCHEMA,
    HONEST_SCOPE_LIMIT as BORING_BRIDGE_LIMIT,
    canonical_record_bytes,
    seal_boring_bundle,
    sha256_prefixed,
    verify_boring_bundle,
    verify_single_record_inclusion,
)
from .quote_provenance import (
    BIT_HASH_MISMATCH,
    BIT_INVALID_DATE,
    BIT_NON_VERBATIM,
    BIT_SHORT_QUOTE,
    HONEST_SCOPE_LIMIT as QUOTE_PROVENANCE_LIMIT,
    CitationLintResult,
    RuleCitation,
    StandingRule,
    is_valid_iso_date,
    lint_citation,
    lint_citations,
    lint_instruction_document,
    sha256_text,
)

HONEST_SCOPE_LIMITS = {
    "quote_provenance": QUOTE_PROVENANCE_LIMIT,
    "anti_softness": ANTI_SOFTNESS_LIMIT,
    "boring_bridge": BORING_BRIDGE_LIMIT,
}

__all__ = [
    "BIT_HASH_MISMATCH",
    "BIT_INVALID_DATE",
    "BIT_NON_VERBATIM",
    "BIT_SHORT_QUOTE",
    "BUNDLE_SCHEMA",
    "DIRECT_FALSIFICATION_MARKERS",
    "HEDGING_PHRASES",
    "HONEST_SCOPE_LIMITS",
    "SYCOPHANCY_PHRASES",
    "TIDY_REDEMPTION_PHRASES",
    "CitationLintResult",
    "CriticScore",
    "RuleCitation",
    "StandingRule",
    "audit_dialogue_turns",
    "canonical_record_bytes",
    "evaluate_transcript",
    "is_valid_iso_date",
    "lint_citation",
    "lint_citations",
    "lint_instruction_document",
    "seal_boring_bundle",
    "sha256_prefixed",
    "sha256_text",
    "verify_boring_bundle",
    "verify_single_record_inclusion",
]
