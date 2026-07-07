# HARNESS — Layer B: the verified-inference contribution

> **Canonical overview: [PROJECT.md](PROJECT.md)** (§1–2 synthesize this). Original design/thesis doc, kept for depth.

> This is the part worth publishing. The model (Layer A) is cheap and
> replaceable; the harness is where frontier *output* is manufactured from
> non-frontier *weights*. The claim: on any task with an oracle,
> `verified_inference(local_model) ≥ single_shot(frontier_model)` — and unlike
> the frontier single shot, every accepted answer ships a re-checkable proof.

## Why this can win (the mechanism, not the wish)

A single forward pass spends a fixed, small compute budget and returns one
sample from the model's distribution. A frontier model wins that game because
its distribution is sharper. We do not try to sharpen the distribution (that
needs scale we do not have). We change the game: spend *test-time* compute to
draw many candidates and let a **real oracle** — not the model's own
confidence — decide. On verifiable tasks the oracle is ground truth, so the
system's accuracy is bounded below by `P(at least one of N candidates passes)`,
which rises fast in N whenever the base model has non-trivial pass@k. Retrieval
supplies the facts the weights never stored. The result is frontier-caliber
*answers* on the verifiable slice, with a proof attached.

Two novelty claims to defend in the write-up:
1. **Verifier-guided search that escalates by oracle signal**, not by token
   count — cheap oracle (compile) gates expensive oracle (full test suite)
   gates the most expensive (property/proof), so search compute concentrates
   where the reward gradient is real.
2. **Every accepted answer carries a re-checkable proof envelope** (the
   operator's reconcile applied to inference): the receipt IS the artifact, so
   a third party re-runs the verifier and reproduces the verdict. Frontier
   single-shot cannot do this.

## The loop (perceive → propose → verify → carry proof)

```
task ─▶ RETRIEVE context ─▶ PROPOSE k candidates ─▶ VERIFY (escalating oracle)
          │                        ▲                      │
          │                        └── refine on failing ─┘  (bounded rounds)
          └─▶ accept best PASSING candidate + proof envelope, else UNVERIFIABLE
```

- **Retrieve.** `index` for in-ecosystem code/symbols/context envelopes;
  `gather` for external knowledge with source receipts. Retrieved spans enter
  the prompt as grounded context; their receipts enter the proof envelope.
- **Propose.** The local QLoRA model samples `k` candidates (temperature +
  nucleus). k, temperature scale with remaining budget.
- **Verify.** The candidate is scored by the oracle for its task class (below).
  Verification is the reward — no learned reward model in the accept path.
- **Refine.** On failure, the failing oracle output (compiler error, failing
  test, counterexample) is fed back for a bounded number of repair rounds.
- **Carry proof.** The accepted candidate is emitted with a proof envelope that
  a third party can re-run to reproduce PASS. No receipt → no accept.

## Verifier registry (one oracle per task class)

| Task class            | Oracle (verifier)                          | Backend |
|-----------------------|--------------------------------------------|---------|
| Python code           | run tests in a sandbox; type-check         | pytest / mypy |
| Rust code             | `cargo build` then `cargo test`            | cargo |
| Proofs / formal math  | proof checker accepts the term             | Lean / Coq |
| Numeric / algebra     | independent numeric or symbolic check      | sympy / mpmath |
| Judgment / synthesis  | register→steelman→measure→witness verdict  | `crucible` |
| Strategy (no oracle)  | self-play / simulation outcome check       | task sim |

The registry is the extensibility surface: a new domain = a new oracle, same
loop. This is exactly how the biology / experimentation track reuses Layer B —
a domain verifier (assay simulator, unit/dimension checker, constraint solver)
drops into the registry and the search machinery is unchanged.

## Search: escalate compute where reward gradient is real

Budget B (candidate-evaluations). Escalate strategy by task difficulty signal:
1. **best-of-N** — sample N, keep any that pass the full oracle. Baseline.
2. **beam / repair** — keep top-scoring partials by cheap oracle (compiles,
   partial tests), expand and repair them under the expensive oracle.
3. **verifier-guided (MCTS-lite)** — tree over edit/repair actions, value =
   oracle reward (fraction of tests passing, or proof progress), UCB selection.
   Reserved for tasks where cheap-oracle signal is dense enough to guide.

Escalation rule: run the cheapest oracle first; only spend the next tier on
candidates that clear the current one. Compile before test; test before
property/proof. Compute concentrates on live candidates.

## Reward shaping (dense where possible, binary at accept)

- Terminal accept reward is **binary and oracle-defined** (pass / not-pass) —
  no reward hacking in the accept path.
- Intermediate guidance may be **dense** (fraction of tests passing, number of
  type errors, proof-obligations discharged) to steer beam/MCTS, but a dense
  win never accepts; only the terminal oracle accepts.

## Proof envelope (the receipt)

Every accepted answer emits, to E:, a JSON envelope:
`{task_id, retrieved[] (with source receipts), candidate, oracle, oracle_cmd,
oracle_output_hash, verdict:PASS, budget_spent, model_ref, seed}`. Re-running
`oracle_cmd` on `candidate` must reproduce `verdict`. `crucible` witnesses the
envelope (MATCH / DRIFT / UNVERIFIABLE). This is the operator's reconcile loop
closed at inference time.

## Eval protocol (the publishable result)

- **Benchmark:** oracle-backed tasks only — held-out code tasks with hidden
  test suites, a proof set, a numeric set. No task without an oracle enters.
- **Comparison:** `verified_inference(local 32B QLoRA)` vs
  `single_shot(frontier)` on identical tasks, matched wall-clock and matched
  token budget reported separately.
- **Metrics:** pass rate; pass@1-equivalent at fixed budget; compute-to-first-
  pass; and the receipt property (fraction of accepts a third party reproduces
  — target 100% by construction).
- **Ablations:** no-retrieval, no-escalation (flat best-of-N), no-refine,
  smaller k. Each isolates one mechanism's contribution.

## Open-ended reasoning (the second focus) rides this same spine

Unverifiable open-ended reasoning is not reachable in the *weights* at this
scale — true, and not the claim. The claim is that a large fraction of what
*looks* open-ended decomposes into sub-goals that DO have oracles (a strategy
whose steps are simulatable, a synthesis whose claims are individually
checkable via `gather` receipts + `crucible` witness). The harness attacks the
verifiable decomposition and marks the irreducibly-unverifiable remainder
honestly as UNVERIFIABLE rather than bluffing. That honesty boundary is itself
a differentiator against a frontier model that will confidently fabricate.

## Build order (after Phase 2 adapter exists)

1. Verifier registry + Python/Rust oracles in a sandbox (real backends first).
2. Retrieval adapters over `index` + `gather` into the prompt + envelope.
3. best-of-N accept loop + proof envelope + `crucible` witness. Ship this;
   it already beats single-shot on the code slice.
4. Escalation (cheap→expensive oracle gating) + bounded repair.
5. verifier-guided search (MCTS-lite) where cheap-oracle signal is dense.
6. Eval harness + ablations → write-up.
