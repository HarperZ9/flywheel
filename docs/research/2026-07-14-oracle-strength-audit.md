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

Probable to definite coverage gaps (the finding):

- **json_string_escape: definite.** `< 0x20` to `<= 0x20` escapes the
  space character; the mutant passed, so no hidden test's expected
  output contains a literal space. Space is the most common character
  in real strings.
- days_in_month: `year < 1` to `year <= 1` rejects year 1, a valid
  year; the boundary is untested.
- kv_event_fold: `len(ev) < 1` to `<= 1` rejects all single-token
  events; either they are all invalid by contract or the case is
  untested.
- bipartite_strict: `1 - color[u]` to `1 + color[u]` destroys the
  parity argument; passing suggests odd-cycle-at-depth is undertested.
- portal_min_moves: `u + 1 < n` to `u - 1 < n` erases a bounds guard;
  passing suggests boundary traversal is undertested or silently
  tolerated.

## What happens next, and what deliberately does not

The five gap candidates get strengthened hidden tests in an explicit
lane version bump (hard_v3), never in place: hard_v2's oracle source
hash is pinned inside every adjudicated artifact from this morning, and
comparability across runs outranks tidiness. Until the bump, the five
tasks carry their flag in the audit artifact, and any claim resting
specifically on them can be discounted by the reader with the artifact
in hand.

The honest comparison: 12.7% mutant-pass on first audit, against 24.4%
false-pass found on the field's flagship leaderboard, with zero
nothing-code acceptances. The lane's floor is real but not perfect, and
now it is measured instead of assumed.
