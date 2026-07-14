# Oracle strength audit: the hard lane's floor, measured (2026-07-14)

Every uplift number this platform has published stands on the hard_v2
oracles refusing wrong code. UTBoost found false-pass patches behind
24.4% of a major leaderboard's entries; this audit turns the same
instrument on our own lane. Artifact:
`artifacts/audit/oracle_strength_20260714-100838.json`
(script: `scripts/oracle_strength_audit.py`).

## Result

| Probe class | Outcome |
|---|---|
| empty module | 0 of 110 accepted |
| return-None admission stub | 0 of 110 accepted |
| constant returns (0, "", []) | 0 of 110 accepted |
| broken references | 0 |
| one-operator mutant accepted | 14 of 110 (12.7%) |
| fully clean | 96 of 110 |

Zero hard flags: no oracle accepted nothing-code. The admission gates
(`oracle_can_fail` and friends) held across the whole lane. The mutant
channel needs case-by-case reading, done below from the exact mutated
lines.

## The 14 mutant passes, classified

Provably neutral mutations (the audit tool's artifact, not a gap):

- count_islands, knight_min_moves, grid_bfs_steps, spread_radius:
  `r + dr` to `r - dr` over a direction set symmetric under negation;
  the neighbor set is unchanged. (high)
- luhn_valid: `d > 9` to `d >= 9` where d is a doubled digit and can
  only be even; d == 9 is unreachable. (high)
- div_round_half_away: sign flag flips only when the numerator is zero,
  and zero has no sign in integer math. (high)

Structurally neutral, moderate confidence (guarded or prefix-equal):

- semver_compare: the mutated comparison runs only under a prior
  inequality guard, where < and <= coincide.
- natural_compare: the tie-break index mutation `j - i` to `j + i`
  orders identically because equal prefixes force equal i on both sides.
- reduce_fraction: `den < 0` to `den <= 0` differs only at den == 0,
  which the task's contract excludes upstream.

Real coverage gaps, confirmed by trace (the finding):

- **json_string_escape: definite.** `< 0x20` to `<= 0x20` escapes the
  space character; the mutant passed, so no hidden test's expected
  output contains a literal space. Space is the most common character
  in real strings.
- **days_in_month: definite.** `year < 1` to `year <= 1` rejects
  year 1, a valid year; the boundary was untested.

Initially flagged as probable gaps, resolved to NEUTRAL on full
mechanical trace (recorded because overcounting gaps is also a
classification error):

- kv_event_fold: a one-element event raises ValueError under both the
  original and the mutant; only the code path differs, never the
  outcome. No behavioral test can distinguish them.
- bipartite_strict: the reference is breadth-first, so `1 + color`
  makes color equal depth, and color-equality on an edge is exactly
  depth-parity equality. The mutant is semantically equivalent for
  this implementation.
- portal_min_moves: the erased upper bound admits one phantom cell
  beyond the board into a dict-based frontier; on a board fully
  connected by unit steps the phantom detour is never on a shortest
  path, so outputs are unchanged.

## What happened next

The two real gaps are closed in **hard_v3**
(`tasks/curated/hard_v3.jsonl`), an explicit version bump, never an
in-place edit: hard_v2's oracle source hash is pinned inside every
adjudicated artifact from this morning, and comparability across runs
outranks tidiness. `tests/test_hard_v3_upgrades.py` proves three
things: the strengthened references still clear every admission gate,
the exact mutants that passed v2 are refused by v3, and the v3 lane
differs from v2 in precisely the two fixed records and nothing else.

The honest comparison: 12.7% mutant-pass on first audit, against 24.4%
false-pass found on the field's flagship leaderboard, with zero
nothing-code acceptances. The lane's floor is real but not perfect, and
now it is measured instead of assumed.
