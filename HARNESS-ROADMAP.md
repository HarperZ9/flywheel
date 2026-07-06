# HARNESS-ROADMAP — Layer B composition plan (durable)

> Operationalizes the Layer-B (verified-inference harness) build. This extends
> `HARNESS.md` (the loop, verifier registry, escalation, proof envelope, eval)
> with the composition discipline the Conservation-of-Faithfulness law demands,
> a checkable milestone sequence, and the traps to engineer against. Read after
> `ROADMAP.md` and `HARNESS.md`. Live cursor for Layer B lives in `STATE.md`.

The thesis (restated): frontier **weights** are unreachable on 24 GB; frontier
**output** on verifiable tasks is not. The gap is closed at inference time by a
harness where a local model proposes and REAL oracles dispose, and every accept
ships a re-checkable proof. The harness — not the base model — is the moat
(C2: even the frontier cannot self-certify, so a local model + oracle-harness
beats single-shot on verifiable tasks). This file is how that moat is built.

## 0. The composition spine — the one architectural addition that matters

`HARNESS.md` already has the terminal proof envelope. For end-to-end
faithfulness the **Layer Composition Law (§4.1)** requires a *carried criterion
chain*: each stage consumes the prior stage's receipt and emits its own, so the
final envelope is a **chain of witnessed transitions**, not a terminal blob.

```
task -> [retrieve-receipt] -> [propose-receipt] -> [verify-receipt] -> [accept-receipt]
        (gather/index)       (model_ref,seed,k)    (oracle,cmd,hash)    (verdict + chain)
```

Each link is witnessed by `crucible` (the reconcile organ) at its boundary.
`no-receipt -> no-accept` becomes the **binary-collapse guard at every link**,
not only the terminal one. Per **§4.2**, each task-domain carries a **scope
condition** in the envelope (the injection-preserving / genericity condition
that forbids collapse modes); `crucible` refuses the chain if a stage violated
it. The frontier single-shot has no chain to inspect; we ship a chain anyone
can re-walk. This is the moat, operationally.

## 1. Component map — exists vs build, by lever

| Lever (from the law)           | Exists (compose, don't rebuild)        | Build                                                       |
|--------------------------------|----------------------------------------|-------------------------------------------------------------|
| External oracle (C2)           | `crucible`; pytest/cargo/Lean backends | Verifier registry v1 + sandboxed runners; one oracle/class  |
| Carried chain (§4.1)           | `emet` (witness), `forum` (ledger)     | Spanning receipt ledger + per-stage reconcile hooks         |
| Independent perspectives (§5.1, §8) | `index` + `gather` (diverse retrieval) | Diversified proposer (≠ retrieval/temp/route) + correlation detector + voice-cap gate |
| Named-criterion adapters (§6.1)| research lanes (discovery/learning/causal/QEC) | criterion-adapter interface: new domain = new oracle + scope, same loop |
| Cost -> ~0 (MEMORY-SUBSTRATE)  | —                                      | receipt cache (content-addressed) + prefix-cache serving backend (vLLM/SGLang) |

## 2. Milestone sequence — each with a falsifier + promotion-ladder target

Labels per the proof-carrying-research-loops discipline
(SOURCE_LEAD -> HYPOTHESIS -> IDENTITY -> PROBE_MATCH -> CRUCIBLE_MATCH ->
LAW_CANDIDATE -> PROMOTED_LAW).

- **M0 — Proposer online.** Local model served over HTTP; `/generate` returns
  `{text, seed, model_ref, prompt_hash}`. Determinism is the falsifier.
  *Falsifier:* a fixed prompt + fixed seed reproduces the same output, twice.
  *Target:* PROBE_MATCH. Unblocks M1. Proposer-agnostic (14B base now; swap
  trained adapter / 32B later). Prefix-cache + RadixAttention = M5.

- **M1 — Minimal witnessed loop (the seed).** task -> `index` retrieve -> M0
  proposes 1 -> pytest oracle in sandbox -> envelope -> `crucible` witness ->
  MATCH/DRIFT/UNVERIFIABLE. Smallest end-to-end receipt.
  *Falsifier:* on a held-out code slice, a third party re-runs `oracle_cmd` and
  reproduces the verdict — target 100%. *Target:* CRUCIBLE_MATCH. This alone
  already beats single-shot on the code slice and is the demo.

- **M2 — Spanning ledger (the spine, §0).** Receipt becomes a per-stage chain;
  `crucible` witnesses each boundary; scope-condition field added per task type.
  *Falsifier:* inject one corrupted/fake stage receipt -> the chain must collapse
  to UNVERIFIABLE, never pass. *Target:* CRUCIBLE_MATCH (binary-collapse guard).

- **M3 — Diversified best-of-N (independence, not count).** k candidates from
  ≠ retrieval slices + ≠ temperature (+ ≠ route when available); correlation
  detector flags near-identical sets; voice-cap gate prevents wrong-attractor
  convergence (§8).
  *Falsifier:* on a task where correlated-N converges wrong, diversified-N + gate
  either finds the right answer or returns UNVERIFIABLE — never confident-wrong.
  *Target:* CRUCIBLE_MATCH.

- **M4 — Escalation (cheap -> expensive oracle gating).** compile -> test ->
  property/proof; spend the next tier only on live candidates.
  *Falsifier:* compute-to-first-pass drops vs flat best-of-N at matched budget;
  no dense-reward accept ever overrides the terminal oracle. *Target:* PROBE_MATCH.

- **M5 — Receipt cache + cost -> ~0 (MEMORY-SUBSTRATE P4.0/P4.1).** Content-
  addressed verified-result store (keys bind `task ⊕ context ⊕ model_ref ⊕
  oracle_cmd`); prefix-cache serving backend (vLLM/SGLang RadixAttention).
  *Falsifier:* a repeated task returns a re-checked receipt at ~0 search cost and
  never serves a stale verdict (any key drift -> miss). *Target:* CRUCIBLE_MATCH.
  (This is what makes deep verified search fit one 24 GB card. Likely needs
  WSL2 for the serving backend on this box.)

- **M6 — Verifier-guided search (MCTS-lite) where cheap-oracle signal is dense.**
  *Falsifier:* beats best-of-N at matched budget only on classes with dense
  cheap-oracle signal; no improvement elsewhere (honest scoping). *Target:* PROBE_MATCH.

- **M7 — Eval + ablations (Phase 5, the publishable result).**
  `verified_inference(local)` vs `single_shot(frontier)`, oracle-backed tasks
  only, matched wall-clock + token budget reported separately. Ablations:
  no-retrieval, no-escalation, no-refine, flat-N, no-cache.
  *Falsifier (whole program):* if `single_shot(frontier)` >=
  `verified_inference(local)` on the oracle-backed slice at matched budget, the
  thesis is DRIFT. *Target:* the result, whatever it is.

## 3. Traps engineered against (concrete)

- **C2 — no learned model in the accept path.** No reward model, learned
  verifier, or logprob threshold ever accepts. Dense reward steers search; only
  the terminal oracle accepts. (Already in `HARNESS.md` reward-shaping — inviolate.)
- **§4.2 — composition is not automatic.** Each task class encodes + checks its
  scope condition; never assume stacking stages composes. M2's falsifier enforces.
- **§8 — correlated-N is fake agreement.** M3's correlation detector + voice-cap
  gate. Near-identical candidate sets -> weak signal -> escalate diversity or
  UNVERIFIABLE, never accept.
- **§6 — never pick the criterion from inside.** Oracle/scope is always
  operator-named; the harness exposes proxy-alignment, never hides it.

## 4. Proposer reality + the honest product claim

- M0 runs on the **14B base today** (it loads; the harness is proposer-agnostic).
  Swap in a trained adapter / the 32B later — M1-M7 do not change, so no work is
  lost to the 32B VRAM wall (parked; see HANDOFF.md corrected diagnosis).
- The honest claim M1 enables (the one a skeptic respects): *on oracle-backed
  code tasks, a local model + witnessed verify-loop matches or beats frontier
  single-shot, every accept ships a re-checkable receipt, UNVERIFIABLE when it
  cannot.* Not "autonomous employee." The boring bridge, with receipts.

## 5. Cross-references, invariants, status

- Design: `HARNESS.md` (loop/registry/escalation/envelope/eval),
  `ROADMAP.md` (phase plan, Layer A vs B), `MEMORY-SUBSTRATE.md` (cost -> ~0).
- Theory: Conservation-of-Faithfulness (the law, §2/§4/§6), Witness-and-
  Verification (bid-vs-bound, the reconcile spine), Proof-Carrying Research
  Loops (the promotion ladder used above).
- Invariants (never violate): no receipt -> no accept; no learned model in the
  accept path (C2); the harness never authors the criterion (§6); nothing large
  on C: (E: is the run drive); corpus source identifiers stay proprietary.

Status: M0 in progress. Each milestone carries its falsifier and is promoted
only when the falsifier fails to fire against runnable evidence. Proof before
trust, applied to the roadmap itself.
