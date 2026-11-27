# Sharded Proof Replay and Hypothesis Mutator (`harness.proof_mutator`)

`harness/proof_mutator/` provides pure-Python standard-library sharded proof-certificate replay and six-class adversarial mutation testing for `buildlang.gpu-tv-cert/v1` and `buildlang.superopt-cert/v1` proof artifacts. Replay digests remain bit-identical across shard counts (`shards=1` matches `shards=4`), and the scorecard fails closed if any mutant survives.

## Modules

`sharded_replay.py` verifies GPU shader and superoptimizer certificates across configurable worker shards, checking schema headers, constant-time SHA-256 parity, monotone non-negative MIR costs, rewrite step counts, valid `R<id>_*` rule identifiers, and ULP bounds while sealing a worker-count-invariant `replay_attestation_sha256`.

`mutant_engine.py` synthesizes six deterministic adversarial mutant classes per artifact without altering source inputs: `sign_flip`, `cost_inversion`, `sha256_1bit_flip`, `step_drop`, `rule_id_swap`, and `ulp_bound_inflation`.

`kill_scorecard.py` runs any proof verifier callable across all generated mutants, enforces `kill_rate == 1.0` fail-closed, seals `scorecard_attestation_sha256`, and includes `permissive_weak_verifier` as a planted weak-verifier negative control.

## Usage

```python
from pathlib import Path
from harness.proof_mutator import (
    evaluate_mutant_kill_scorecard,
    load_gpu_proof_corpus,
    verify_worker_count_invariance,
)

corpus = load_gpu_proof_corpus(Path("workstation-gpu-emitted"))
assert verify_worker_count_invariance(corpus, shard_counts=(1, 4))
assert evaluate_mutant_kill_scorecard(corpus).kill_rate == 1.0
```

## Honest Scope Limits

`sharded_replay.py`, `mutant_engine.py`, and `kill_scorecard.py` verify serialized certificate invariants and measure verifier sensitivity over six defined mutant classes. They do not re-run e-graph saturation, SMT provers, or GPU shader compilers.
