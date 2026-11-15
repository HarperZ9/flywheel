# Research-Claim Proof Packet `demo-triangular`

**Verdict: MATCH - Promotion: CRUCIBLE_MATCH** -- The identity held under a bounded numeric probe (n=1..1000).

- **Scope:** One arithmetic identity; bounded probe; not a general proof.

## Statement

> For all n >= 1, sum_{k=1}^n k = n(n+1)/2.

## Sources

- OEIS A000217 (triangular numbers) <https://oeis.org/A000217>

## Attempts

- `a1` numeric-probe -> bounded: checked n=1..1000 exhaustively

## Checks

| Checker | Status | Verdict |
| --- | --- | --- |
| numeric-probe | pass | MATCH |

## Uncertainty

- bounded probe only; not a general proof for all n

_Verdict re-derivable via crucible from the emitted thesis + measurements. A failed or UNVERIFIABLE packet still preserves the sources, attempts, and next checks -- a negative result is evidence, not a discarded run._