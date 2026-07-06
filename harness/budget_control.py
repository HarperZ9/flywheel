"""budget_control.py — correlation-collapse as a verification-budget controller (#5).

The one honestly-novel slice (the mechanism itself — adaptive/successive-halving
budget allocation — is well-known prior art): use the wrong-attractor correlation
statistic (search.max_pairwise_correlation) as the trigger. When a candidate wave
COLLAPSES (near-identical = fake agreement, §8), verifying more of the same wastes
budget; REDIRECT it to a diversity-boosted re-sample instead. When the wave is
diverse, proceed to verify. Budget is CONSERVED (reallocation, not addition).

Honest scope: this is adaptive allocation with a correlation trigger; it only wins
when the diversity boost actually decorrelates the next wave (it may not — that is
the falsifiable risk, and flat-N is the fallback). Never accepts on correlation;
the terminal oracle still disposes (C2).
"""
from __future__ import annotations

from dataclasses import dataclass

COLLAPSE_THRESHOLD = 0.85    # matches search.CORRELATION_THRESHOLD (§8 voice-cap)
TEMP_STEP = 0.3
TEMP_CAP = 1.3


@dataclass
class Step:
    action: str          # "boost_diversity" | "verify"
    next_temp: float
    spend: int           # verifications spent THIS step


def steer(correlation: float, remaining_budget: int, temp: float, *,
          collapse_threshold: float = COLLAPSE_THRESHOLD) -> Step:
    """One control decision. A collapsed wave -> boost diversity (raise temp) and
    spend only 1 to re-sample; a healthy wave -> verify (spend the remaining
    budget on the diverse candidates)."""
    if remaining_budget <= 0:
        return Step("verify", temp, 0)
    if correlation >= collapse_threshold:
        return Step("boost_diversity", min(temp + TEMP_STEP, TEMP_CAP), 1)
    return Step("verify", temp, remaining_budget)


def run_steered(wave_correlations: list[float], budget: int,
                start_temp: float = 0.4) -> dict:
    """Drive successive waves under a FIXED budget, steering by each wave's
    correlation. Returns the plan: steps taken, budget spent (<= budget), and
    whether it escalated diversity. `wave_correlations` is the observed
    correlation of each wave in order (the harness measures it per wave)."""
    temp = start_temp
    remaining = budget
    steps: list[Step] = []
    boosts = 0
    for corr in wave_correlations:
        if remaining <= 0:
            break
        s = steer(corr, remaining, temp)
        steps.append(s)
        remaining -= s.spend
        temp = s.next_temp
        if s.action == "boost_diversity":
            boosts += 1
        else:
            break                       # verified a healthy wave -> done
    spent = budget - remaining
    return {"steps": steps, "spent": spent, "budget": budget,
            "diversity_boosts": boosts, "conserved": spent <= budget}


def flat_spend(n_waves: int, budget: int) -> int:
    """Flat-N baseline: spend the whole budget verifying every wave regardless of
    collapse. The comparison point for the efficiency claim."""
    return budget
