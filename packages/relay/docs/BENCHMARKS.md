# Benchmarks: fewer numbers, each one a receipt

relay will not out-spend a frontier lab on SWE-bench or ARC, and it will not
astroturf a leaderboard. The posture here is the opposite: publish fewer numbers,
and make each one a receipt a stranger can re-run. Every number that ships from
this project comes with its interval, its denominator, and a line stating what it
does not prove.

As of 2026-08-27 the measured numbers below are not yet published. That is an
honest null, not a placeholder: the harness to produce them exists, the runs do
not. This document is the methodology, so that when a number appears you can check
how it was made.

## The integrity benchmark (the axis we top by construction)

The claim relay can defend is not "solves more" but "does not bank a gamed pass."
The integrity benchmark measures exactly that.

- Corpus: a fixed set of reward-hacking trajectories, each a run that turns a check
  green without solving the task: editing the grading test, `xfail`-ing the failing
  case, `sys.exit(0)` before the assertion, monkeypatching the framework, or
  claiming work the ledger never recorded.
- Metric: refusal rate, the fraction of gamed passes relay's accept gate correctly
  refuses. A harness that reports `exit 0` as success banks these; relay refuses
  them, and the refusal is itself a re-derivable receipt.
- Why it is honest: the corpus is public and adversarial, and the metric is a
  refusal, so a higher score costs a vendor its own gamed passes. Nobody optimizing
  a leaderboard wants to publish it.

## The edit-format self-run (a borrowed claim becomes an owned receipt)

Content-hash line edits are reported elsewhere to cut output tokens and lift edit
success. Rather than cite that number, relay will measure its own: apply-success
and output tokens per edit format across the four relay ships, whole-file
(`write_file`), search-replace (`edit_file`), hash-anchored (`edit_lines` /
`edit_plan`), and fail-closed unified-diff (`apply_diff`), on relay's own task
set, with each run's hash-chained ledger attached as the evidence file.

The apply layer is built and tested; the numbers are what wait. Each format's
applier already fails closed rather than fuzzing, so the axis the run measures is
whether a given model emits an edit the applier accepts, not whether a fuzzy match
papers over a near miss.

Honest null: this run is pending. It needs a live model backend to produce the
per-format numbers, and none is attached here, so no uplift is claimed. The
methodology and the four appliers, not a conclusion, are what is committed today.

## An honest SWE-bench slice

A small, fixed subset of SWE-bench Verified, reported with the resolved rate and
the accept-gate verdict per instance, so a green result also shows it was not
gamed. The cost and the denominator ship with it.

Honest null kept in advance: if the slice shows no uplift over a frontier harness
on raw resolve rate, that is what will be reported. The relay claim is not "we
solve more." It is "when we say solved, it is re-verifiable."

## The rule every number follows

- Interval, denominator, and a does-not-prove line, always.
- The run that produced the number ships with it as an `.rvc` certificate a reader
  can verify offline (see [ACCOUNTABILITY.md](ACCOUNTABILITY.md)).
- No number appears here that a visitor cannot reproduce from the attached run.
