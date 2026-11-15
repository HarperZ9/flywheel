# Research-Claim Proof Packet `demo-collatz`

**Verdict: UNVERIFIABLE - Promotion: UNVERIFIABLE** -- A bounded probe reached 1; the general claim is not proven.

- **Scope:** Open problem; bounded probe only.

## Statement

> The Collatz map reaches 1 from every positive integer.

## Sources

- Collatz conjecture (open problem) <https://en.wikipedia.org/wiki/Collatz_conjecture>

## Attempts

- `a1` numeric-probe -> bounded: reached 1 for all n <= 1e6
- `a2` lean -> incomplete: no total termination proof

## Checks

| Checker | Status | Verdict |
| --- | --- | --- |
| lean-total-termination | unverifiable | UNVERIFIABLE |

## Uncertainty

- a bounded probe cannot establish the general claim; this remains open

_Verdict re-derivable via crucible from the emitted thesis + measurements. A failed or UNVERIFIABLE packet still preserves the sources, attempts, and next checks -- a negative result is evidence, not a discarded run._