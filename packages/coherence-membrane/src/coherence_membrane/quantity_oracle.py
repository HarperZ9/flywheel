"""dimensional-invariant-v1 -- the tier-2 oracle over Quantity.

Re-derives dimensional/numeric invariants and emits a Certificate. SOUNDNESS: a
*dimensional* VERIFIED is exact (Fraction compare); a *magnitude* VERIFIED is
'within rel_tol' and the tol is carried in the evidence -- a float compare is not
dressed as a proof. Any non-finite value or unsupported input ⇒ UNVERIFIABLE."""
from __future__ import annotations

import math
from dataclasses import dataclass

from .certificate import Certificate, Verdict
from .quantity import DimensionError, Quantity

_ORACLE = "dimensional-invariant-v1"


@dataclass(frozen=True)
class QuantityClaim:
    """A checkable claim 'lhs equals rhs' (dimension AND magnitude)."""

    claim: str
    lhs: Quantity
    rhs: Quantity
    rel_tol: float = 1e-9


def check_same_dimension(a: Quantity, b: Quantity) -> Certificate:
    claim = f"dim({a.dim}) == dim({b.dim})"
    if a.dim == b.dim:
        return Certificate(claim, Verdict.VERIFIED, _ORACLE, (("dim", str(a.dim)),))
    return Certificate(claim, Verdict.REFUTED, _ORACLE,
                       (("lhs_dim", str(a.dim)), ("rhs_dim", str(b.dim))))


def check_dimensionless(q: Quantity) -> Certificate:
    claim = f"dimensionless({q.dim})"
    if q.dim.is_dimensionless:
        return Certificate(claim, Verdict.VERIFIED, _ORACLE, (("dim", "1"),))
    return Certificate(claim, Verdict.REFUTED, _ORACLE, (("dim", str(q.dim)),))


def check_equation(lhs: Quantity, rhs: Quantity, *, rel_tol: float = 1e-9) -> Certificate:
    """VERIFIED iff dims exactly equal AND magnitudes within rel_tol."""
    claim = f"{lhs.magnitude} [{lhs.dim}] == {rhs.magnitude} [{rhs.dim}]"
    if not (math.isfinite(lhs.magnitude) and math.isfinite(rhs.magnitude)):
        return Certificate(claim, Verdict.UNVERIFIABLE, _ORACLE,
                           (("reason", "non-finite magnitude"),))
    if not math.isfinite(rel_tol) or rel_tol < 0.0:   # an inf/nan/neg tol would launder a false VERIFIED
        return Certificate(claim, Verdict.UNVERIFIABLE, _ORACLE,
                           (("reason", f"invalid rel_tol: {rel_tol!r}"),))
    if lhs.dim != rhs.dim:
        return Certificate(claim, Verdict.REFUTED, _ORACLE,
                           (("lhs_dim", str(lhs.dim)), ("rhs_dim", str(rhs.dim))))
    if math.isclose(lhs.magnitude, rhs.magnitude, rel_tol=rel_tol, abs_tol=0.0):
        return Certificate(claim, Verdict.VERIFIED, _ORACLE,
                           (("magnitude", repr(lhs.magnitude)), ("rel_tol", repr(rel_tol))))
    denom = max(abs(lhs.magnitude), abs(rhs.magnitude)) or 1.0
    residual = abs(lhs.magnitude - rhs.magnitude) / denom
    return Certificate(claim, Verdict.REFUTED, _ORACLE,
                       (("lhs", repr(lhs.magnitude)), ("rhs", repr(rhs.magnitude)),
                        ("rel_residual", repr(residual))))


def check_consistent(thunk) -> Certificate:
    """Run a zero-arg Quantity construction; DimensionError ⇒ REFUTED (an
    inconsistent construction, certified without crashing the caller); a returned
    Quantity ⇒ VERIFIED; any other exception ⇒ UNVERIFIABLE (not our invariant)."""
    claim = "dimensionally-consistent construction"
    try:
        result = thunk()
    except DimensionError as exc:
        return Certificate(claim, Verdict.REFUTED, _ORACLE, (("violation", str(exc)),))
    except Exception as exc:
        return Certificate(claim, Verdict.UNVERIFIABLE, _ORACLE, (("reason", repr(exc)),))
    if isinstance(result, Quantity):
        return Certificate(claim, Verdict.VERIFIED, _ORACLE, (("result_dim", str(result.dim)),))
    return Certificate(claim, Verdict.UNVERIFIABLE, _ORACLE,
                       (("reason", "thunk did not return a Quantity"),))
