"""Tier-3 cross-check: a verdict only when independent methods AGREE.

Trust-minimization made executable. One solver is one trusted base -- a bug in it is
a false VERIFIED with authority. Requiring independent methods to agree shrinks the
trusted base to "they are not all wrong the same way"; any DISAGREEMENT is a caught
bug (UNVERIFIABLE + discrepancy), never a guess. This is why a native cross-check is
more trustworthy than depending on one external solver: we use methods, we never
trust one. The harness is method-agnostic -- an external oracle (Z3/Lean/BDD) may be
supplied as ONE non-trusted voice, corroborated or it does not count; nothing here
imports it."""
from __future__ import annotations

from dataclasses import dataclass

from .certificate import Certificate, Verdict
from .propositional import check_validity, is_formula, show
from .resolution import res_check_validity
from .truth_table import tt_check_validity

_ORACLE = "cross-check-v1"


@dataclass(frozen=True)
class Method:
    """A named, independent decision procedure: name + (formula, *, max_atoms) -> Certificate."""

    name: str
    decide: object


DEFAULT_METHODS = (
    Method("dpll", check_validity),
    Method("truth-table", tt_check_validity),
    Method("resolution", res_check_validity),
)


def _consensus(claim: str, named: list, *, min_agree: int) -> Certificate:
    verifs = [n for n, c in named if c.verdict is Verdict.VERIFIED]
    refs = [n for n, c in named if c.verdict is Verdict.REFUTED]
    methods_ev = tuple((f"method:{n}", c.verdict.value) for n, c in named)
    if verifs and refs:   # a contradiction among independent methods is a caught bug
        return Certificate(claim, Verdict.UNVERIFIABLE, _ORACLE,
                           (("discrepancy", f"VERIFIED={verifs} REFUTED={refs}"),) + methods_ev)
    if len(verifs) >= min_agree and not refs:
        return Certificate(claim, Verdict.VERIFIED, _ORACLE, (("agree", ",".join(verifs)),) + methods_ev)
    if len(refs) >= min_agree and not verifs:
        return Certificate(claim, Verdict.REFUTED, _ORACLE, (("agree", ",".join(refs)),) + methods_ev)
    return Certificate(claim, Verdict.UNVERIFIABLE, _ORACLE,
                       (("reason", f"insufficient corroboration (need >={min_agree} agreeing, zero dissent)"),) + methods_ev)


def cross_check_validity(formula, *, methods=DEFAULT_METHODS, max_atoms: int = 16,
                         min_agree: int = 2) -> Certificate:
    """Cross-check a validity claim across independent methods. VERIFIED/REFUTED only
    on >=min_agree agreement with zero dissent; a split or a shortfall -> UNVERIFIABLE.
    A method that raises is captured as its own UNVERIFIABLE (fail-closed). Requires
    min_agree >= 2 -- single-source trust is the tier's forbidden state."""
    if min_agree < 2:
        raise ValueError("min_agree must be >= 2 (cross-check requires corroboration)")
    if not is_formula(formula):
        return Certificate(str(formula), Verdict.UNVERIFIABLE, _ORACLE, (("reason", "not a formula"),))
    try:
        claim = show(formula)
    except RecursionError:   # a pathologically deep formula must degrade, not crash the harness
        return Certificate(type(formula).__name__, Verdict.UNVERIFIABLE, _ORACLE,
                           (("reason", "formula too deeply nested"),))
    named: list = []
    for m in methods:
        try:
            named.append((m.name, m.decide(formula, max_atoms=max_atoms)))
        except Exception as exc:
            named.append((m.name, Certificate(claim, Verdict.UNVERIFIABLE, _ORACLE,
                                              (("error", f"{m.name}: {exc!r}"),))))
    return _consensus(claim, named, min_agree=min_agree)
