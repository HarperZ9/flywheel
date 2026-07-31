# Benchmarks

The honest state of this model's measurement, kept current.

## What exists today

One behavioral receipt: a **deterministic generation smoke**. Served through
Ollama, the model was asked to generate at temperature 0 with a fixed seed
(seed 7, 64 tokens), twice, and the two outputs were byte-compared. Verdict:
**MATCH** (generation hash prefix `403b2e8b21df9f55`). That establishes the
served model is deterministic and reproducible, nothing more.

## What does not exist yet

No task benchmark has been run against this model. There is no HumanEval score,
no hard-set score, no leaderboard number. **We claim no capability uplift over
the base `Qwen2.5-Coder-32B-Instruct`.** Any such comparison must come from
executed benchmark artifacts, and none exist for the 32B.

This is the deliberate difference from the
[14B](https://huggingface.co/zaindanaharper/flywheel-local-coder-14b), which
does carry executed benchmark evidence (with intervals, and the JSON to re-run
each number). The 32B ships as a verified, retraceable build; the scored
evidence is a separate, future measurement.

## How the numbers will arrive, when they do

The same way the 14B's did, and no other way:

- Run under a fixed harness with a published task set and a real oracle
  (propose, run the test, accept only what passes).
- Every number ships with the JSON it came from and the command to re-run it.
- Confidence intervals attached; a difference against base whose interval
  includes zero is reported as no uplift, not as a win.

Until an executed benchmark artifact is attached here, treat this model on its
provenance and its determinism receipt, not on any performance claim.
