"""vocab.py -- one verdict vocabulary, and how the four older sets map onto it.

The spine reuses `harness.verdict.Verdict` (PASS, FAIL, UNDECIDED,
UNVERIFIABLE) instead of adding a fifth set. Every tool in the family already
emits one of four vocabularies. Each maps onto the spine here, by a table a
reviewer can read in one screen.

The map loses detail on purpose: `warn` and `needs-human` both become
UNDECIDED. A spine record therefore carries the source term beside the spine
verdict, and the verifier checks that the pair agrees with this table. The
spine verdict is what a consumer branches on. The source term is what a person
reads to learn why.

Rule for the map, in one line each:
  PASS          the check ran and decided in favour (pass, MATCH, allow)
  FAIL          the check ran and decided against (fail, DRIFT, deny)
  UNDECIDED     the check ran and declined to dispose (warn, needs-human)
  UNVERIFIABLE  the check could not run, or does not apply (unverified,
                unknown, not-applicable)
"""
from __future__ import annotations

from ..verdict import Verdict

# Flywheel's own four, from harness/verdict.py. The identity map.
FLYWHEEL = "flywheel"
# MATCH/DRIFT/UNVERIFIABLE: emet, crucible, index, gather corpus, telos proof,
# proof-surface, mneme drift, Flywheel replay and chain validation. emet's
# receipt lattice (SPEC section 17.3) is the same three facts under longer names.
INTEGRITY = "integrity"
# The organ-bundle entry status shared by gather, crucible, index, forum, learn
# and Flywheel's lesson_interop.py.
ORGAN_BUNDLE = "organ-bundle"
# Pre-action gates: accountable-surface, the coherence-membrane write gate.
GATE = "gate"

VOCABULARIES: dict[str, dict[str, Verdict]] = {
    FLYWHEEL: {
        "PASS": Verdict.PASS,
        "FAIL": Verdict.FAIL,
        "UNDECIDED": Verdict.UNDECIDED,
        "UNVERIFIABLE": Verdict.UNVERIFIABLE,
    },
    INTEGRITY: {
        "MATCH": Verdict.PASS,
        "DRIFT": Verdict.FAIL,
        "UNVERIFIABLE": Verdict.UNVERIFIABLE,
        "RECEIPT_VALID": Verdict.PASS,
        "RECEIPT_TAMPERED": Verdict.FAIL,
        "RECEIPT_UNVERIFIABLE": Verdict.UNVERIFIABLE,
    },
    ORGAN_BUNDLE: {
        "pass": Verdict.PASS,
        "fail": Verdict.FAIL,
        "warn": Verdict.UNDECIDED,
        "needs-human": Verdict.UNDECIDED,
        "unverified": Verdict.UNVERIFIABLE,
        "not-applicable": Verdict.UNVERIFIABLE,
        "unknown": Verdict.UNVERIFIABLE,
    },
    GATE: {
        "allow": Verdict.PASS,
        "deny": Verdict.FAIL,
        "needs-human": Verdict.UNDECIDED,
    },
}

# Precedence when several checks fold into one verdict. A confirmed difference
# outranks an inability to check (emet SPEC section 5 and 17.3), and an
# inability to check outranks a check that declined.
_RANK = {Verdict.FAIL: 3, Verdict.UNVERIFIABLE: 2, Verdict.UNDECIDED: 1,
         Verdict.PASS: 0}


class VocabularyError(ValueError):
    """A vocabulary or term the spine has no mapping for."""


def to_spine(vocabulary: str, term: str) -> Verdict:
    """Map one source term onto the spine. Unknown names raise, never guess."""
    table = VOCABULARIES.get(vocabulary)
    if table is None:
        raise VocabularyError(f"unknown verdict vocabulary {vocabulary!r}")
    if term not in table:
        raise VocabularyError(
            f"{term!r} is not a term of the {vocabulary} vocabulary")
    return table[term]


def fold(verdicts) -> Verdict:
    """The worst of several verdicts. An empty fold is UNVERIFIABLE."""
    verdicts = [Verdict(v) for v in verdicts]
    if not verdicts:
        return Verdict.UNVERIFIABLE
    return max(verdicts, key=_RANK.__getitem__)


def mapping_rows() -> list[tuple[str, str, str]]:
    """(vocabulary, source term, spine verdict) rows, for docs and tests."""
    return [(name, term, verdict.value)
            for name, table in VOCABULARIES.items()
            for term, verdict in table.items()]
