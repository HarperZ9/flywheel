# Architecture synthesis — assess everything, chase the breakthrough (2026-07-06)

> Output of an 11-agent workflow: map the whole corpus + codebase → 5 competing
> unifying architectures from distinct angles → adjudicate for GENUINE novelty vs
> named prior art → spec + build the winner's kernel. Honest headline first.

## Honest verdict: no breakthrough. The strongest thread is a real composition.

All five candidate architectures self-labelled **strong-synthesis**, and the
adjudicator confirmed it plainly: every one composes modules that already exist
(witness / chain / cache / wiki / search / boot); **none introduces a new
verification primitive.** That is the truth, stated without decoration. What we
*do* have is a genuine, unpublished COMPOSITION — new moves over known parts.

The unifying thread (thesis #1): every stage in the harness — boot, propose,
policy, transpile, oracle, cache, wiki, escalation — is secretly one primitive,
a **witnessed criterion-conserving transform** (perceive → transform under a
named criterion → emit a re-checkable receipt). The frontier question (thesis
#2): does criterion-conservation *compose* end-to-end? Today it does not — every
receipt is an island (`witness_envelope` is called on exactly one envelope per
run; `validate_chain` only checks `prev_hash` equality, never re-witnesses).

## The five theses (all strong-synthesis), ranked by novelty × buildability

| # | Thesis | The genuinely new move | Prior art it is NOT |
|---|---|---|---|
| **3 ★** | **Proof-Addressed Memory** | Use the C2 invariant as a THEOREM: acceptance is oracle-gated and prompt-independent, so the verified result can be keyed on the oracle-certified fact with the prompt ABSENT. | input-addressed caches (RAG query-key, RadixAttention prefix-KV, content-addressed stores, verifier memoization, proof-carrying code) — none has an oracle certifying two prompts yield the same fact |
| 2 | **Transitive Witness** | Re-witness the whole dependency cone of a citation DAG; reclassify an envelope UNVERIFIABLE because an *ancestor* drifted, not itself. Criterion-conservation as a closure property. | M1 witness (one oracle), M2 validate_chain (one run's links), M5 cache (one key) — all verify ONE thing |
| 1 | **Witnessed Transform protocol** | One `WitnessedTransform` protocol every stage registers under; generalize the oracle special-case to all stages. | StageReceipt + validate_chain already record + pointer-check; this is the cleanest unification but the most restatement-adjacent |
| 4 | **Provenance-Keyed Flywheel** | Bind a `knowledge_hash` into `cache_key` so a wiki DRIFT cheaply invalidates dependent cached results (fixes a second latent cache bug: cache_key binds test files but NOT retrieved knowledge). | RadixAttention / RAG / living-wikis each do ONE of cache/retrieve/verify, never keyed together |
| 5 | **Correlation-Steered Compute** | Use the wrong-attractor correlation statistic as a BUDGET controller (reallocate fixed verification budget when candidates collapse), not just a veto. | best-of-N treats N + temperature as fixed hyperparameters set before seeing candidates |

## Winner built + proven + wired: Proof-Addressed Memory

`harness/proof_cache.py` (+`tests/test_proof_cache.py`, 6 falsifiers). The load-
bearing claim, executable: two prompts differing ONLY in a volatile attribution
header, same task+oracle, collapse to ONE cache entry — and a hit is
re-witnessed, served only on MATCH.

- Dissolves the live **F2 bug** (0% agent cache-hit: volatile per-turn headers
  leaked into `prompt_hash`). Wired into `run_loop`: proof-lookup before the
  prompt-keyed lookup; proof-insert alongside. Prompt-independent oracles only.
- **C2 preserved**: a proof-hit re-runs the oracle (`witness_envelope`) and
  serves only on MATCH — never blind, never stale. A proof-hit skips the
  proposer (the expensive part) but pays one oracle re-run (the honest tax; it
  is cheaper-not-free, not "zero cost").
- **Scope condition (the falsifier's teeth)**: sound only for oracles whose
  `verify` ignores the prompt. `PROMPT_INDEPENDENT = {pytest, stub}`; anything
  else falls back to prompt-keying. `test_no_prompt_independent_oracle_reads_
  the_prompt` greps `oracle.py` for `task.prompt` — if a future oracle reads it,
  the test FAILS and forces an opt-out, narrowing rather than corrupting.
- **The falsifier earned its keep**: it caught a real key-inconsistency —
  `PytestOracle` augments the command to `... --junitxml=... -q` and run_loop
  stores that as `envelope.oracle_cmd`, so insert (envelope cmd) and lookup
  (task cmd) keyed differently and every lookup missed. Fixed by keying both on
  the declared `task.oracle_cmd`.

## Roadmap (the honest next moves, in order)

1. **#2 Transitive Witness** — strongest guarantee; the citation edges exist
   on-disk (`retrieved`/envelope refs) but are never followed. ~120 lines DFS +
   fold over the dependency cone. This is what makes criterion-conservation
   actually compose — the closest thing to a real contribution here.
2. **#4 Provenance-Keyed Flywheel** — fixes the second latent cache bug
   (`cache_key` omits `knowledge_hash`); composes with proof-addressing and the
   verified wiki so a DRIFTed source cheaply invalidates dependent results.
3. **#1 Witnessed-Transform protocol** — the unification, once #2/#4 prove the
   composition holds; lowest novelty-per-line, highest clarity payoff.
4. **#5 Correlation-Steered Compute** — adaptive budget; narrowest novelty.

## The ceiling, stated honestly

This is compounding engineering synthesis, not a new verification primitive. The
value is real (a live bug dissolved, criterion-conservation on a path to
composing) but the operator's own standard applies to this work too: **receipts
are the floor.** The breakthrough, if one exists, is #2's closure property —
prove that a frontier of witnessed transforms re-checks as one object — and that
is the next thing to build, not to claim.
