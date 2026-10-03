# Re-check a seeded run and a claimed improvement

## Replay certificate

`harness/certificates/replay.py` compares two runs of the same seeded
computation. Each run records digests of its weights, inputs and seed, the
determinism flags it ran under, its device and driver, and a digest of the
decoded state at each fixed checkpoint.

| Verdict | When |
| --- | --- |
| MATCH | Every checkpoint digest agrees and both runs declare the determinism flags |
| DRIFT | A checkpoint differs, the counts differ, or the runs disagree on weights, inputs or seed |
| UNVERIFIABLE | A run lacks a determinism flag or recorded no checkpoints |

The determinism flags are `deterministic_algorithms`, `cublas_workspace_config`
and `cudnn_deterministic`. For PyTorch that means
`torch.use_deterministic_algorithms(True)`, `CUBLAS_WORKSPACE_CONFIG=:4096:8` and
`torch.backends.cudnn.deterministic = True`.

Every verdict carries this line: "Same computation ran twice. Says nothing about
whether the answer is right or generalizes." Bit-exact replay depends on the
hardware and driver. A DRIFT between two devices carries a note that it may be a
scope limit rather than a changed computation.

Evidence: in a separate test outside Flywheel, two same-seed runs of a
180,736-parameter cellular automaton under these flags matched at 30 of 30
checkpoints (Wilson 95% interval 0.886 to 1.000). One model on one machine.

## Re-derivation gate (preview)

`flywheel rederive run.json` re-checks a claim that a configuration improves a
metric over a baseline. It accepts only when:

1. a verifier the claimant does not control computed the metric;
2. the seeds are the gate's own (a claim that names its seed list is refused);
3. the mean paired gain on those seeds is larger than a luck margin of
   2 x (sample standard deviation of the baseline's per-seed results) / sqrt(n);
4. a replay of the claimant's stated seed returns MATCH.

```json
{
  "gate": {"seeds": [2001, 2002, 2003, 2004, 2005, 2006, 2007, 2008]},
  "claim": {"id": "three-epochs"},
  "baseline": {"2001": 0.861, "...": 0.869},
  "treated":  {"2001": 0.885, "...": 0.886},
  "replay": {"claimed": {"...": "replay record"}, "replayed": {"...": "replay record"}}
}
```

Exit code 0 means ACCEPT, 1 means REJECT, 2 means the claim was refused. Every
verdict says `"status": "preview"` and names its margin and the margin's basis.

Why the standard error and not the raw seed spread: on the first small test, a
real gain of 0.0137 was smaller than twice the seed spread (0.021), so that
margin rejected a true claim. The standard-error margin accepted it and still
rejected the three planted false claims. That test had 1 true and 3 false
claims; it shows the mechanism, not its error rates.
