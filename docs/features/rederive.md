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
