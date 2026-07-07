"""authorization_cost.py — the compute tax of permission-instead-of-accountability.

The operator's claim, made measurable: substituting ex-ante PERMISSION for ex-post
ACCOUNTABILITY taxes compute, and the tax grows with how much work is shared or
repeated. The mechanism is amortization, and it is structural, not rhetorical:

- ACCOUNTABILITY: a verified result is a RE-CHECKABLE, content-addressed proof.
  Anyone can re-verify it, so a repeat is reused trustlessly (the receipt cache
  hits) and costs ~0. Total cost scales with UNIQUE work.
- PERMISSION: an authorization is the authority's word for one act in one context.
  It is not an independently re-checkable artifact, so it cannot be reused
  trustlessly — re-doing the act (or a similar one) needs a fresh decision. Total
  cost scales with EVERY act.

So on a workload with repeat fraction r, accountability pays for (1-r)*N and
permission pays for N. The ratio is N/unique, which in a deep-search/flywheel
system (r -> high) is large — "immense", as claimed.

HONEST BOUND: when nothing repeats (all-novel work), the two regimes cost the
same. The win is specifically on shared/repeated work; there is no free lunch on
genuinely new work. And permission remains correct for the irreversible tail,
where ex-post accountability cannot recover the act — this measures the REVERSIBLE,
re-checkable majority where permission is a misapplication.

Grounded: `unique` is exactly what the real ReceiptCache dedups by (content-
addressed key), verified in the test against ReceiptCache itself.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RegimeCost:
    n_acts: int
    unique_acts: int
    repeat_fraction: float
    accountability_cost: float     # pay verify only for UNIQUE (re-checkable reuse)
    permission_cost: float         # pay approval for EVERY act (no trustless reuse)
    tax_ratio: float               # permission / accountability (>= 1)

    def report(self) -> str:
        return (f"{self.n_acts} acts, {self.unique_acts} unique "
                f"(repeat {self.repeat_fraction:.0%}): accountability "
                f"{self.accountability_cost:g} vs permission {self.permission_cost:g} "
                f"-> {self.tax_ratio:.2f}x permission tax")


def regime_cost(workload_keys: list[str], *, verify_cost: float = 1.0,
                approval_cost: float = 1.0) -> RegimeCost:
    """Cost the same workload under both regimes. `workload_keys` are the content-
    addresses of each act (identical key = a repeat, exactly what the cache dedups)."""
    n = len(workload_keys)
    unique = len(set(workload_keys))
    accountability = unique * verify_cost              # re-checkable proof reused free
    permission = n * approval_cost                     # authorization not trustlessly reusable
    tax = (permission / accountability) if accountability else float("inf")
    return RegimeCost(
        n_acts=n, unique_acts=unique,
        repeat_fraction=(1 - unique / n) if n else 0.0,
        accountability_cost=accountability, permission_cost=permission,
        tax_ratio=tax)


def crossover_repeat_fraction(target_tax: float) -> float:
    """The repeat fraction r at which the permission tax reaches `target_tax`.
    tax = N/unique = 1/(1-r)  =>  r = 1 - 1/tax. So 2x tax needs r=0.5, 10x needs
    r=0.9. Shows WHY a flywheel (high r) makes the gap immense."""
    if target_tax <= 1:
        return 0.0
    return 1.0 - 1.0 / target_tax
