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
