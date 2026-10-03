# Search mode: who picks the answer and who checks it

When Flywheel samples several candidates for one task, two jobs happen: one
check picks a candidate, and one check decides whether that pick is right. If
the same check does both, the result cannot lose to its own choice, so it says
little about whether the answer is right.

## With hidden tests

A task that carries `held_out_cmd` gets two checks:

1. The visible tests (`oracle_cmd`) run on each candidate in proposal order.
   The first one that passes is the pick. Temperature 0.0 is sampled first, so a
   tie goes to the greedy answer.
2. The hidden tests (`held_out_cmd`) run once, on the pick only. Their verdict is
   the result. If the pick fails them, the run ends FAIL; Flywheel does not try
   the next candidate against the hidden tests.

The receipt's search stage records `selection: visible-selects-held-out-decides`
and the hidden check's verdict and output hash.

## Without hidden tests

The one check picks and decides, as before. The search stage records
`selection: self-scored`, so a reader can see the pick and the verdict came from
the same check.

## Pool arms

`best_of_k` in `harness/pool_arms.py` takes a held-out `score`. A self-scored run
must be asked for by name with `self_scored=True`.

## Evidence and limits

In a separate test outside Flywheel (142 programming problems, one 14B local
model, 16 samples each, visible tests picking and hidden tests scoring), picking
by visible tests beat picking by the model's own confidence by 0.106 (95%
interval 0.056 to 0.155) and beat a single attempt by 0.063 (0.014 to 0.106).
That result used one model and one task family. It is not a measurement of
Flywheel's shipped benchmark.

Tasks without hidden tests gain nothing from this change beyond the honest
label.

## Optional: skip duplicate candidates

`python -m harness.cli <task-dir> --search --prune-duplicates 2` (or `ArmConfig(prune_m=2)`) skips
the check for a candidate whose partial code, with comments, whitespace and names
normalized, matches two earlier candidates at 25, 50 or 75% of its length. At
most three candidates are skipped per task, and a skipped candidate always leaves
at least two live members of its group. The search stage records how many were
skipped and their tokens.

It is off by default. In the separate test above, pruning at 2 was simulated
offline from finished samples: 0.772x the tokens for an accuracy drop of 0.014.
Flywheel's proposers return whole answers, so here pruning saves check runs
only; the generation tokens are already spent. A live token saving needs a
streaming proposer and is unmeasured.

## Optional: stop drawing once the pick is settled

The visible tests pick the first passing candidate in proposal order. Any
candidate drawn after that first pass can never change the pick, so drawing it
spends a sample and changes nothing. The effort gate stops the draw early:

- `first-pass`: draw the temperature-0 candidate. If it passes the visible
  tests, stop; otherwise draw the other three.
- `sequential`: stop at the first candidate that passes the visible tests.

`python -m harness.cli <task-dir> --search --effort-gate sequential` (or
`ArmConfig(effort_gate="sequential")`). The hidden tests still run once, on the
pick, so the gate cannot add an accept the hidden tests reject. The search
stage records `effort_gate` with the planned, drawn and skipped sample counts.
The gate is off by default.

Measured on one model (a local 14B coder) on the 110-problem hard_v2 set, with
every candidate logged and the bar set before the run: keep at least 90% of
search's gain while drawing at most half its samples.

| Gate | Gain kept | Samples drawn vs full search [95%] | Bar |
|:--|:--|:--|:--|
| `sequential` | 7 of 7 | 0.446 [0.391, 0.502] | met |
| `first-pass` | 7 of 7 | 0.509 [0.441, 0.577] | missed by 0.009 |

Use `sequential`. Search's gain on this set is 7 problems, so "all of it kept"
cannot rule out losing one or two. At temperature 0 the local server returned
the same text on 80 of 110 problems, so a redrawn candidate can differ from a
logged one. The full record is in
`project-docs/records/search-effort-gate/RUN-LOG.md`.
