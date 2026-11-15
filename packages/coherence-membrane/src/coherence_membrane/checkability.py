"""checkability -- "re-checkable proof" means re-checkable IN PRACTICE (a budget guard).

A `Certificate` can be perfectly SOUND yet useless to a third party: if its witness is
too large or expensive to re-derive within an available budget, "anyone can re-check
it" is false in practice. This is the strong-vs-weak-solution distinction: a STRONG
(re-checkable-within-budget) certificate is genuinely `VERIFIED`; a WEAK one (sound but
bounded-and-incomplete to re-check) is `UNVERIFIABLE-in-practice`, NOT `VERIFIED`. This
module is the verifier-ladder analogue of the cardinal rule "soundness over
completeness", pushed to the CHECKER's resource bound: when re-checking would exceed
what the verifier can afford, the honest verdict is UNVERIFIABLE.

`bounded_checkability` is a thin combinator over `Certificate`/`Verdict`, like
`compose` / `cross_check_local`. The budget is INJECTED exactly as `distance` /
`deviation` are in `novelty` / `structural_fitness` -- no global policy is baked in; a
caller with more resources passes a larger budget. It can ONLY DOWNGRADE:

  * `VERIFIED` whose `recheck_cost` exceeds (or is UNKNOWN under) the budget
        -> `UNVERIFIABLE`  (reason ``unverifiable-in-practice: re-check cost N > budget B``).
  * `VERIFIED` whose `recheck_cost` is within budget -> stays `VERIFIED` (STRONG).
  * `REFUTED` / `UNVERIFIABLE` -> passed through UNCHANGED (a refutation or a non-
        decision is not made "more checkable" by a budget; the guard never upgrades).

Fail-closed: an ABSENT or unparsable cost under a FINITE budget is treated as UNKNOWN
and downgrades (you cannot certify re-checkability you cannot bound). The ONLY way a
`VERIFIED` survives is a present, finite cost <= a finite budget -- or an explicitly
infinite (unbounded) budget, the opt-out that says "re-check cost is not a constraint
here". Soundness-preserving by construction: it NEVER turns a non-`VERIFIED` into a
`VERIFIED`, and never raises (TOTAL); any internal error degrades to UNVERIFIABLE.

Attribution (study + cite, never strip): 2swap, "Beating Connect 4 with Brute Force"
(id ``i9pBeuBeupY``) and "I Solved Connect 4" (id ``KaljD3Q3ct0``) -- the strong-vs-
weak solution / certificate-size distinction. Remediates teardown finding C1 ("a
receipt too large to re-check is UNVERIFIABLE-in-practice, not VERIFIED"). Stdlib only.
"""
from __future__ import annotations

import math

from .certificate import Certificate, Verdict

_ORACLE_SUFFIX = "+bounded-checkability-v1"

# The evidence key a producing oracle SHOULD set to declare its witness's re-check cost
# (witness size / steps to re-verify, as a nonnegative number). Absent => unknown.
RECHECK_COST_KEY = "recheck_cost"

# Evidence markers added on a downgrade, so the cause is auditable from the certificate.
_STRENGTH_KEY = "checkability"
_STRONG = "strong: re-checkable within budget"
_WEAK = "weak: unverifiable-in-practice"


def recheck_cost_of(cert: Certificate) -> float | None:
    """Read the declared re-check cost from a certificate's evidence, or ``None`` if it
    is absent / unparsable / not a nonnegative real (any of which is treated as UNKNOWN
    by the guard, i.e. fail-closed under a finite budget). Pure + deterministic."""
    for key, value in cert.evidence:
        if key == RECHECK_COST_KEY:
            try:
                cost = float(value)
            except (TypeError, ValueError):
                return None
            if not math.isfinite(cost) or cost < 0:
                return None
            return cost
    return None


def with_recheck_cost(cert: Certificate, cost: float) -> Certificate:
    """Additive helper for a producing oracle: return a NEW certificate carrying a
    declared `recheck_cost` in its evidence (claim/verdict/oracle byte-identical). The
    cost must be a nonnegative, finite real -- validated loudly at the door so the guard
    downstream only ever sees a sound declaration or a true absence."""
    if not isinstance(cost, (int, float)) or isinstance(cost, bool) or not math.isfinite(cost) or cost < 0:
        raise ValueError(f"recheck_cost must be a nonnegative finite real, got {cost!r}")
    return Certificate(
        cert.claim, cert.verdict, cert.oracle,
        cert.evidence + ((RECHECK_COST_KEY, repr(float(cost))),),
    )


def bounded_checkability(cert: Certificate, *, budget: float) -> Certificate:
    """Downgrade a `VERIFIED` certificate to `UNVERIFIABLE` when its witness cannot be
    re-checked within `budget`. DOWNGRADE-ONLY; never upgrades; never raises.

    `budget` is the INJECTED re-check resource bound (witness size / steps the verifier
    can afford), a nonnegative number; ``float('inf')`` means "no re-check-cost
    constraint" (the explicit opt-out -- every `VERIFIED` then survives). A non-real /
    negative / NaN budget is itself treated as fail-closed: a `VERIFIED` becomes
    `UNVERIFIABLE` (a budget you cannot interpret cannot license a re-check).

    Rules:
      * verdict is not `VERIFIED` (`REFUTED` / `UNVERIFIABLE`) -> returned UNCHANGED.
      * `VERIFIED`, cost present & finite & <= budget -> stays `VERIFIED`, tagged STRONG.
      * `VERIFIED`, cost ABSENT/unknown under a finite budget -> `UNVERIFIABLE`
            (fail-closed: cannot certify re-checkability you cannot bound).
      * `VERIFIED`, cost > budget -> `UNVERIFIABLE` (reason carries N and B).
    The original verdict + the reason are recorded in evidence on a downgrade; a kept
    `VERIFIED` is byte-stable apart from the appended `checkability=strong` marker."""
    try:
        if cert.verdict is not Verdict.VERIFIED:
            # Never upgrade: a refutation or a non-decision passes straight through.
            return cert

        budget_ok = isinstance(budget, (int, float)) and not isinstance(budget, bool) \
            and not math.isnan(budget) and budget >= 0
        # An infinite budget is the explicit opt-out: no re-check-cost constraint.
        if budget_ok and math.isinf(budget):
            return Certificate(
                cert.claim, cert.verdict, cert.oracle + _ORACLE_SUFFIX,
                cert.evidence + ((_STRENGTH_KEY, _STRONG), ("budget", "inf")),
            )

        cost = recheck_cost_of(cert)

        if not budget_ok:
            return _downgrade(cert, cost, budget, reason="uninterpretable budget")
        if cost is None:
            return _downgrade(cert, None, budget, reason="re-check cost unknown")
        if cost > budget:
            return _downgrade(cert, cost, budget, reason="over budget")

        # STRONG: a present, finite, within-budget cost -> genuinely re-checkable.
        return Certificate(
            cert.claim, cert.verdict, cert.oracle + _ORACLE_SUFFIX,
            cert.evidence + ((_STRENGTH_KEY, _STRONG),
                             ("recheck_cost_checked", repr(float(cost))),
                             ("budget", repr(float(budget)))),
        )
    except Exception as exc:  # TOTAL: nothing escapes; an error fails closed.
        # The fallback must not itself trust the (possibly malformed) certificate shape:
        # rebuild from defensively-coerced fields so the except handler can never raise.
        claim = getattr(cert, "claim", "?")
        claim = claim if isinstance(claim, str) else str(claim)
        oracle = getattr(cert, "oracle", "?")
        oracle = (oracle if isinstance(oracle, str) else str(oracle)) + _ORACLE_SUFFIX
        return Certificate(
            claim, Verdict.UNVERIFIABLE, oracle,
            ((_STRENGTH_KEY, _WEAK), ("reason", "internal error"), ("error", repr(exc))),
        )


def _downgrade(cert: Certificate, cost: float | None, budget, *, reason: str) -> Certificate:
    """Build the downgraded `UNVERIFIABLE` certificate, recording the original verdict,
    the human reason, and the cost/budget so the cause is auditable. Soundness core:
    the verdict is forced to UNVERIFIABLE -- this function is reached ONLY from a
    `VERIFIED` input, so it strictly downgrades."""
    cost_str = "unknown" if cost is None else f"{cost!r}"
    budget_str = f"{budget!r}"
    detail = f"unverifiable-in-practice: re-check cost {cost_str} > budget {budget_str} ({reason})"
    return Certificate(
        cert.claim, Verdict.UNVERIFIABLE, cert.oracle + _ORACLE_SUFFIX,
        cert.evidence + ((_STRENGTH_KEY, _WEAK),
                         ("reason", detail),
                         ("downgraded_from", Verdict.VERIFIED.value)),
    )
