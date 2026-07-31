# CERTIFIED COMMONS (CC‑1)
### Recommended architecture, final call

---

## 1. The ruling

**CC‑1 takes COMMONS as the spine, CERT‑1 as the evidence protocol, and ASSAY as the instrumentation, and it fixes the one flaw all three share by making the same choice serve three purposes at once.**

The spine is COMMONS: the primary artifact is a criterion‑pinned verification environment whose receipts a stranger re‑derives offline, with the training run as a first‑class consumer rather than the deliverable. That wins because it is the only slant that survives being wrong about the model, and the literature says we will probably be wrong: elicitation‑vs‑expansion is unresolved, spurious rewards have moved Qwen math scores, and a null training run only the operator can reproduce is a diary entry. From CERT‑1 I graft the entire evidence discipline: construction certificates as the flagship oracle family, verifier QA enforced in code before any verdict becomes reward, the control‑arm set, the frozen preregistration with a hash‑pinned analysis script, and the "shortest honest path" instinct that keeps the module count down. From ASSAY I graft the cost meter, the scope‑bound audit‑once lift, named invalidation with typed reason codes, and the non‑collapsible tier field, but **demoted from headline to instrument** because on a millisecond stdlib checker the oracle call is not the scarce resource and a frozen‑mix replay series falls by construction. The convergence that decides it: choosing construction certificates makes the oracle a **data checker that never executes candidate code**, and that single choice simultaneously fixes COMMONS's fatal security flaw (`verify` was remote code execution aimed at every stranger), CERT‑1's cost problem, and the offline‑verifiability gap that nobody currently ships. One decision, three fatal flaws closed.

---

## 2. Components

Substrate claims below marked **[verified]** were re‑read at HEAD in this session; the rest are inherited from the panel's line‑cited reads (high confidence, independently reported by two or more lenses).

`Ph` = phase (0 ground, 1 first proof, 2 hardening, 3 distribution). Stdlib harness respects the 300‑line gate; `train/` is gate‑exempt.

### Layer 0 — seam repairs (nothing new until these hold)

| Path | Purpose | Composes | Lines | Ph |
|---|---|---|---|---|
| `C:\dev\local-model\harness\verdict.py` | Single definition site for `Verdict{PASS,FAIL,UNDECIDED,UNVERIFIABLE}`, `Execution{COMPLETED,TIMEOUT,CRASHED,RESOURCE_EXCEEDED,TOOLCHAIN_MISSING,HARNESS_ERROR}`, `Attribution{CANDIDATE,HARNESS,ENVIRONMENT}`, typed reason codes. | new primitive | 90 | 0 |
| `harness\oracle.py` **(MODIFY)** | `OracleResult` gains `verdict`, `execution`, `attribution`, `raw_stdout_sha256`, `duration_ns`, `objective`. `passed` kept as a property that **raises** on non‑PASS/FAIL so all call sites surface at once. `run_env()` becomes a deny‑by‑default allowlist. `shell=True` → argv list. `start_new_session=True` on POSIX. rlimits / Job Object. | **[verified]** today: `passed: bool`, `verdict()→PASS\|FAIL`, `run_env()={**os.environ,...}` | +70/−25 | 0 |
| `harness\advantages.py` | `grpo_advantages(rewards, estimator)` with `drgrpo` (r − mean, no std division, **no per‑sequence length normalization**), `grpo_std` (legacy, kept as a control arm), `gspo`. Estimator recorded in the receipt. | split out of `rl_from_oracle.py` **[verified]** `(r-mean)/(pstdev+EPS)` at :47‑60 | 120 | 0 |
| `harness\rl_from_oracle.py` **(MODIFY)** | `collect()` takes a reward callable instead of hardcoding binary; **one temperature per group, fresh seeds per step**; UNDECIDED → advantage exactly 0.0 and loss‑masked; CANDIDATE‑attributable execution failure → FAIL; HARNESS‑attributable → dropped **and written to the exclusion ledger**. `budget_schedule` removed from the training path. | **[verified]** `:197 reward = 1.0 if ....passed else 0.0`; `:145 PolicyOptimizer` Protocol, zero impls | +80/−40 | 0 |
| `harness\gateway_auth.py` + `gateway.py` **(MODIFY)** | Bearer token at 0600, Host allowlist (kills DNS rebinding), `application/json` required on every state‑changing route (kills CORS‑simple CSRF). Env surfaces get their **own process and their own four‑route table**, never the 2,391‑line gateway. | `harness/gateway.py`, `harness/keychain.py` | 120 + 60 | 0 |
| `.github\workflows\ci.yml` | Matrix ubuntu / macos‑arm64 / windows × py3.10‑3.13. Jobs: targeted slice; **stdlib‑import‑graph assertion** on the verifier path; **clean‑clone network‑disabled bundle verify**; 300‑line gate with current violations grandfathered on a burn‑down list; orphan check (no new harness module with zero non‑test importers); **AST no‑execution assertion** on every `certificates/*` module (no `subprocess`, `socket`, `ctypes`, `pickle`, `eval`, `exec`). | none exists today (panel‑verified, three lenses) | 150 yaml | 0 |

### Layer 1 — criteria and checkers (the accept path)

| Path | Purpose | Composes | Lines | Ph |
|---|---|---|---|---|
| `harness\criteria\spec.py` | **The criterion object.** `criterion_id/version/sha256`, `parent_criterion_sha256`, `change_reason`, family, generator ref + seed ranges, objective direction + normalization + reward mapping **as data not code**, incumbent source, scope bounds, `decision_rule`, `prompt_policy_hash`, license id. Explicit, versioned, hash‑pinned, forkable, contestable. | COMMONS `env_spec`; CERT‑1 registry; `transitive_witness.py` criterion_version + REBASELINE semantics | 180 | 1 |
| `harness\criteria\registry.py` | Versioned incumbent reference set. Two independent citations **or** operator‑computed. Named invalidation codes. **Refuses any non‑CONJUNCTIVE decision rule as reward‑eligible.** Plain JSON so a fork edits data, not Python. | `gather` sealed digests, `index` named invalidation | 190 | 1 |
| `harness\certificates\base.py` | `CertificateOracle` ABC. Pure data checking, exact integer arithmetic, **never executes candidate code**. Rejects out‑of‑envelope declared parameters *before* dispatch. Emits a `coverage` block (predicate exact vs bounded, enumerated fraction, stop reason, the parameter above which the guarantee weakens). | `harness/oracle.py` Oracle Protocol | 150 | 1 |
| `harness\certificates\generators.py` | **Parameterized instance generators with a difficulty knob**, randomized into parameter space absent from published tables. The spec pins generator + seed range, not a static shard. | new | 210 | 1 |
| `harness\certificates\zarankiewicz.py` | K_{s,t}‑free bipartite witness checker, bitset scan. | `certificates/base.py` | 190 | 1 |
| `harness\certificates\const_weight.py` | A(n,d,w) constant‑weight codebook checker. | `certificates/base.py` | 130 | 1 |
| `harness\certificates\independent.py` | Independent reimplementation of each predicate by a **different algorithm**, wired to `RLItem.held_out`, **plus spec‑level mutation testing over the encoding grammar** (two implementations of one spec share spec‑level exploits). Disagreement → UNDECIDED, never positive reward. | `rl_from_oracle.RLItem.held_out` (present, unpopulated) | 210 | 1 |
| `harness\certificates\matmul_adapter.py` | Wraps the **existing** exact‑Fraction matmul tensor checker. Reuses its Strassen/Laderman ladder and `perturb_scheme`/`drop_triple` as the fuzz corpus. Rewriting it was a duplication two lenses caught. | `harness/matmul_oracle.py` | 70 | 1 |
| `harness\oracle_qa.py` | Verifier QA that **precedes** training. Known‑valid generators, near‑miss mutants, planted detectable exploits (duplicate edges, out‑of‑range indices, declared‑vs‑actual mismatch, homoglyph separators, trailing garbage, adversarial size and nesting). Reports false‑accept rate as a **Wilson upper bound at declared confidence with a required n per mutation class**, not a zero‑count boolean. Emits an `OracleQACard`. No card, no reward eligibility, enforced at registry admission. | generalizes `calibration.py` (whose `trustworthy = fp==0 and n>0` is the defect to fix), `adversarial_corpus.py`, `injection_probe.py` shape | 260 | 1 |
| `harness\certificates\ramsey.py` / `gf2_code.py` | Families 3 and 4. | `certificates/base.py` | 140 / 200 | 2 |

### Layer 2 — the record

| Path | Purpose | Composes | Lines | Ph |
|---|---|---|---|---|
| `harness\receipt_fields.py` | Schema constants, enums, derived‑`does_not_prove` rule table. Data only, so `receipt.py` keeps headroom under the gate. | new | 130 | 1 |
| `harness\receipt.py` | `flywheel.receipt/v2` dataclass, canonical JSON, and the **two digests**: `content_digest` (deterministic re‑derivable subset including the verdict) and `attested_digest` (full body, what gets signed). | `envelope.py` (v1 becomes a projection), `merkle.py` | 280 | 1 |
| `harness\ed25519_verify.py` | Vendored pure‑stdlib RFC 8032 **verify only**. This is what makes "stdlib‑only, offline, no install" and "a stranger can check the signature" simultaneously true. All three proposals had these mutually exclusive. | stdlib `hashlib` | 130 | 1 |
| `harness\receipt_sign.py` | Ed25519 mandatory for anything exportable; HMAC local‑only and **stripped at pack time**. Signs `attested_digest`. `signed_over` is fixed in code per schema version, never read from the receipt (JWT alg‑confusion fix). Signer runs as a **separate OS principal**; preferred mode signs the periodic Merkle root, not every receipt inline. | `keychain.py` (+ libsecret / `security` / 0600‑file fallbacks) | 160 | 1 |
| `harness\ledger.py` | Append‑only JSONL, hash chain at **full sha256** (current chain truncates to 16 hex = 64 bits, ~2^32 birthday work), RFC 6962 **consistency proofs** on top of the existing inclusion proofs, signed tree heads, and an **exclusion ledger**: what never got a receipt and why. Selection bias lives in that set. | `chain.py`, `transparency_log.py` (fuzz‑clean per panel) | 220 | 1 |
| `harness\contest.py` | **The inbound refutation channel.** `flywheel contest <bundle>` mints a counter‑receipt signed with the contester's own key, binding the disputed receipt id, their toolchain pin, their raw oracle bytes, their environment fingerprint. Append‑only. Open‑contest count is a published series. | `ledger.py`, `receipt_sign.py` | 150 | 1 |
| `harness\verify_bundle.py` | The offline verifier. Stdlib‑only, zero network, **Tier‑A default: no candidate execution**. Emits a **vector**, not a word: `{rerun, inclusion, consistency, signature, pin, criterion}`, plus the three‑way human summary **MATCH / CANNOT‑CHECK‑HERE / CLAIM‑DOES‑NOT‑HOLD**. Tier‑B execution requires an explicit flag, a named isolate, and prints the argv first. | `verify_receipt.py`, `transparency_log.py`, `ed25519_verify.py` | 250 | 1 |
| `harness\bundle.py` | Pack/unpack `.frb`. Ships criterion.json, oracle pin manifest, inputs, candidate bytes, **raw oracle bytes**, a **vendored `rerun.py` that imports nothing**, inclusion + consistency proofs, STH history, `keys.json` (pubkey, validity window, revoked_at), signature, `does_not_prove`. Hardened: zip‑slip / symlink / absolute‑path defense, size budget, secret scan that **hard‑fails** the pack, path normalization. | `corpus_export.py` shard pattern, `publish_lint.py` | 240 | 1 |
| `harness\why.py` | **`flywheel why <receipt_id>`.** Renders the accept story in one command: criterion + version, provision + pin, input closure, evidence kind, computed coverage, lift chain, denominator, `does_not_prove`, contest status, copyable rerun command. All three proposals asserted "why was this accepted is the cheapest action" and none of them built it. | `ledger.py`, `receipt.py` | 150 | 1 |

### Layer 3 — cost and amortization (instrument, not headline)

| Path | Purpose | Composes | Lines | Ph |
|---|---|---|---|---|
| `harness\cost_meter.py` | **Multi‑denominator**: oracle calls, oracle_ns, cpu_ns, gpu_ns, generated tokens, human minutes. Also the **user‑facing budget**: pre‑spend estimate, a cap that halts (not warns), a live counter, and a cancel that still emits an INCOMPLETE receipt. | `budget_control.py`, `telemetry.py` | 210 | 2 |
| `harness\amortize.py` | Scope‑bound audit‑once lift and certify‑fast‑against‑slow. `cache_key = H(criterion_sha256 ‖ provision_digest ‖ input_closure_digest ‖ analysis_script_sha256 ‖ scope_id)`. Epsilon‑rate forced re‑verification. **A lift transfers cost, never tier.** Two series, never pooled: replay (engineering fact, carries no claim) and transfer (novel input closures only, the only one that can carry a claim). | `proof_cache.py`, `index` named invalidation | 230 | 2 |

### Layer 4 — model adapters (bolt‑on, first class)

| Path | Purpose | Composes | Lines | Ph |
|---|---|---|---|---|
| `harness\adapters\discovery.py` | Metadata discovery ladder, not hand‑written config: local GGUF header KV → Ollama `/api/show` → HF `config.json`/`tokenizer_config.json` → `/v1/models` → measured‑only. `metadata_source` recorded **per field**. | `providers.py`, `endpoint_registry.py`, `model_profiles.py` | 260 | 2 |
| `harness\adapters\negotiation.py` | Effective context by **measurement**: needle‑recall binary search, silent‑truncation detection, rope‑degradation detection. Records `effective_context_measured` beside `declared_context` and never smooths the gap. | `context_governor.py`, `context_envelope.py` | 230 | 2 |
| `harness\adapters\prompt_cache.py` | Cache‑aware prompting: deterministic stable‑prefix order (criterion, tools, evidence, then volatile task), prefix hash, per‑provider cache hints, and **measured hit rate into the denominator**. This is how verification throughput becomes a budget instead of a hope. | `cache.py`, `proof_cache.py`, `prompt_forge.py` | 240 | 2 |
| `harness\adapters\toolcall.py` | Dialect conformance probe: OpenAI tools / Anthropic tool_use / Hermes‑Qwen XML / raw‑JSON fallback. The harness learns which dialect a bolted‑on model honors instead of assuming. | `tool_receipts.py`, `local_tools.py`, `mcp_client.py` | 260 | 2 |
| `harness\adapter_card.py` | The conformance battery and signed AdapterCard. Determinism graded **three‑valued** (deterministic / seeded‑nondeterministic / nondeterministic), not pass‑fail, because vLLM continuous batching would make the modal card `unverified` and kill the field's information. Records `trainable` vs `evaluatable_only`. A model with no card still runs, stamped `adapter_unverified`, but **`adapter_unverified` receipts are inadmissible to uplift, retention, and cost claims**. | `adapter_runtime_matrix.py`, `parity.py` | 250 | 2 |

### Layer 5 — the science

| Path | Purpose | Composes | Lines | Ph |
|---|---|---|---|---|
| `harness\prereg.py` | Freeze and hash the experiment. Pushes the prereg hash to an **external anchor** (public git tag) on freeze day: a commit timestamped by the same person who runs the experiment is a diary entry, not a preregistration. | `chain.py`, `forum` ledger | 180 | 1 |
| `harness\control_arms.py` | The arms as code that **raises**, not as discipline. An uplift claim emitted without a registered and completed control arm is an exception, not a return value. | `uplift_bench.py`, `developmental.py`, `benchmark_hygiene.py` | 250 | 1 |
| `harness\uplift_stats.py` | The actual statistics. `forecast_bootstrap.py` is a Beta‑posterior pass@k forecaster with **no BCa and no cluster resampling** (three lenses verified this independently). New: cluster bootstrap over (instance, seed), **seed‑level spread as the primary uncertainty**, permutation test over seed×arm, exact binomial/Poisson for rare‑event counts, power analysis and MDE. Validated against synthetic data with known coverage before the freeze. | new | 200 | 1 |

### Layer 6 — training (`train/`, gate exempt)

| Path | Purpose | Composes | Lines | Ph |
|---|---|---|---|---|
| `train\reward_gate.py` | **The receipt is on the accept path.** The TRL `reward_func` computes the verdict via a subprocess into the stdlib checker, writes and signs the receipt, appends to the ledger, and returns the reward **only on successful commit**. Any commit failure returns the UNDECIDED sentinel (advantage 0, loss‑masked). This is what makes "no receipt no accept" mechanical instead of an assertion checked after the weights moved. | `receipt.py`, `ledger.py`, `certificates/*` | 210 | 1 |
| `train\policy_optimizer_trl.py` | The first concrete `PolicyOptimizer`. TRL GRPOTrainer + Unsloth + vLLM. Dr.GRPO advantages (no std division **and** no per‑sequence length normalization), DAPO clip‑higher **with DAPO's overlong soft punishment**, dynamic difficulty filtering that **resamples to a full batch** rather than shrinking it, GSPO available for large/MoE, small KL‑to‑reference with `kl_coef` and `reference_policy_hash` logged per step. | `rl_from_oracle.PolicyOptimizer`, `qlora_cpt.py` model build / LoRA presets / `--smoke` | 280 | 1 |
| `train\rollout_audit.py` | The diagnostics that catch silent gradient corruption: vLLM‑vs‑trainer logprob divergence (startup assertion + per‑group receipt field + preregistered abort threshold), truncated importance sampling, clip fraction, ratio histogram, advantage std, grad norm, effective batch size, completion‑length distribution, sync lag. Advantage agreement done correctly: compares the **actual tensor the optimizer consumed** against `harness.advantages` at the same estimator mode, float‑eps tolerance. | `advantages.py` | 200 | 1 |
| `train\entropy_guard.py` | Torch reimplementation of the reheater math (the stdlib module is scalar `list[float]` per token position and cannot run at 150k vocab). Fixes found by the panel: **detach the self‑distillation target** (undetached, the KL is minimized by driving all logits equal, which is policy destruction), unify units to nats, add hysteresis, replace string‑distinctness diversity with a canonicalized measure. `reheater.py` is retained as the **CPU reference oracle** for a numerical‑parity test on a tiny synthetic vocab; both hashes go in the receipt. | `reheater.py` (currently imported by nothing) | 230 | 1 |
| `train\search_baseline.py` | Simulated annealing / evolutionary search over the same generated instances at equal wall clock. Serves double duty: control arm G, and the **source of unpublished incumbents** that fixes contamination. | `certificates/*` | 190 | 1 |

### Layer 7 — surfaces and distribution

| Path | Purpose | Composes | Lines | Ph |
|---|---|---|---|---|
| `harness\cli_entry.py` **(MODIFY)** | `flywheel verify \| why \| contest \| criterion \| oracle qa\|pin\|doctor \| adapter probe\|conform \| bench prereg\|run \| pack \| budget`. Dispatch only. | existing front controller | +110 | 1 |
| `C:\dev\flywheel-desktop\lib\models\receipt_v2.dart` + `lib\views\receipt_detail_view.dart` | The receipt v2 renderer: verdict, evidence kind, denominator, **computed coverage**, `does_not_prove`, why, contest status. `render_status.dart` gains the fourth verdict as a **word and a shape**, not a fourth color. Plus the budget surface: estimate → cap → live meter → cancel. | `receipts_view.dart`, `tokens.dart`, `fw.dart` | ~380 dart | 1 |
| `envs\flywheel_certificates\` | verifiers + OpenEnv adapters, thin shape translation only, pinned to named upstream commits, on their own process. **Pack/Env split**: the Pack ships receipts + replay + verifier and **no plaintext hidden tests**; the Env ships task specs and no receipts. Hidden tests ship as salted commitments. | `criteria/*`, `certificates/*` | 300 / 4 files | 3 |
| `scripts\reproduce.ps1` / `reproduce.sh` | Tier‑0 replay: fuzz suite, replay every certificate, recompute every digest and signature, regenerate the headline table from raw oracle bytes. Minutes on a laptop, no GPU, no network, no account. | `verify_bundle.py`, `uplift_stats.py` | 130 each | 3 |

---

## 3. End‑to‑end data flow

```
CRITERION ──► TASK ──► ROLLOUT ──► VERDICT ──► RECEIPT ──► GRADIENT
                                       │           │
                                       └──► LEDGER ◄┴──► EVAL ──► PUBLICATION
                                              ▲
                                        CONTEST (inbound)
```

**Criterion.** `criteria/spec.py` yields a hash‑pinned criterion: family, generator id + seed range, objective normalization and reward mapping as data, incumbent source, scope bounds, prompt policy. **`gather`** is the intake for incumbent bounds (sealed digests, grounding check) but **proposes into a staging file only**; a **`forum`** human gate promotes it into the registry, because a reward scale extracted from PDFs by a model‑assisted pipeline is a learned model influencing the accept path through the back door.

**Task.** `certificates/generators.py` emits an instance with a difficulty knob. The **`learn`** lane's online difficulty filter keeps the pass rate in the learnable band and supplies predict‑then‑observe calibration; its filter id, hash, and `filter_is_learned` flag are **mandatory denominator fields** so a learned proposer choosing the population is visible rather than invisible. Held‑out instances are split at instance level within regime (primary) and by parameter regime (secondary transfer), sealed by **`crucible`** before training.

**Adapter.** The **model‑adapter layer sits between the task and the rollout** and nowhere else. `adapters/discovery.py` resolves the model to a capability record by probing, `negotiation.py` measures its real context, `prompt_cache.py` orders a stable prefix and reports the measured hit rate, `toolcall.py` picks the dialect the model actually honors. `adapter_card.py` stamps the receipt with `trainable` vs `evaluatable_only`, `adapter_unverified`, `base_weights_digest`, `tokenizer_sha256`, `chat_template_sha256`, and `effective_context_measured`. Any model, any provider, runs; only carded, trainable models produce receipts admissible to a claim.

**Rollout.** G rollouts at **one temperature with fresh seeds per step**. `budget_schedule`'s multi‑temperature grid stays on the selection and eval path where it belongs; using it for a policy‑gradient group makes each member a draw from a different tempered policy and puts the decode config into the advantage.

**Verdict.** Each rollout goes across a subprocess boundary into a stdlib `CertificateOracle`. **No model on the accept path, and no candidate code executed at all.** **`crucible`** is the verdict authority: it issues PASS / FAIL / UNDECIDED / UNVERIFIABLE with attribution, and its ProofMeasure seam carries the integer objective and the coverage block alongside the boolean. The independent reimplementation runs on the same text; disagreement is UNDECIDED, never the majority side. Consensus and quorum oracles are **refused at registry admission** for reward eligibility: votes propose, proofs dispose, and `selector.CONSENSUS_PASS` maps to UNDECIDED at mint time.

**Receipt.** `train/reward_gate.py` builds, signs, chains, and commits the receipt **before returning any reward**. **`forum`** is the ledger of record and the only path to a human‑adjudicated annotation. **`index`** supplies scope bounds, `INPUT_MUTATED` events, and named invalidation from checker source hash to dependent receipts. Raw oracle bytes are hashed by the meter from the subprocess stream before any Python reads them, so `model_readout: false` is structural rather than self‑attested.

**Gradient.** Reward = validity gate × normalized objective ratio to the incumbent, per the criterion's own mapping. UNDECIDED gets advantage exactly 0.0 and is loss‑masked but counted. Candidate‑attributable execution failure scores FAIL. Harness‑attributable failure is dropped and written to the exclusion ledger. Dr.GRPO advantages, DAPO clip‑higher with overlong punishment, small KL leash, entropy guard fires on a hysteretic floor with a detached self‑distillation target.

**Eval.** Reads the ledger, never the trainer. Preregistered paired arms, `uplift_stats.py` computes intervals with seed spread primary. **`crucible`** runs the sealed held‑out assessment. `developmental.curate()` supplies both the retention probe and the rejection‑sampling SFT arm.

**Ledger and contest.** Every receipt appends to a full‑sha256 chain with inclusion and consistency proofs and a signed tree head published to an anchor the operator does not control. **`telos`** is the export: a `.frb` bundle is a self‑contained proof packet with an oracle pin, a criterion, and a proof of position added, and propose‑verify‑promote is exactly the certificate lifecycle. Strangers push **contests** back in as signed counter‑receipts; open contests are a published series.

---

## 4. Receipt schema

`flywheel.receipt/v2`. Canonical JSON: sorted keys, `(",",":")`, UTF‑8, no NaN/Inf, **no floats in any hashed field** (integers and decimal strings only, because cross‑platform float formatting is the likeliest cause of a stranger's replay disagreeing).

**Two digests, because one cannot do both jobs.**
- `content_digest` — sha256 over the deterministic, third‑party‑re‑derivable subset: criterion, provision, evidence kind, inputs, analysis script hash, `raw_oracle.canonical_sha256`, **verdict**, objective, scope. Everything here a stranger recomputes by re‑running the pinned oracle.
- `receipt_id` = sha256(`content_digest` ‖ run_nonce ‖ ledger_seq) — unique per run. Two runs of a nondeterministic oracle over identical inputs get distinct ids and share `content_digest` only when the verdicts match.
- `attested_digest` — sha256 over the full body minus signature. **This is what gets signed.**

```
IDENTITY      schema, schema_version, content_digest, receipt_id, attested_digest,
              created_utc, harness_version, run_id, parent_receipt_id

CRITERION     criterion_id, criterion_version, criterion_sha256,
              parent_criterion_sha256, change_reason,
              decision_rule (CONJUNCTIVE required for reward eligibility),
              objective_direction, objective_normalization, reward_mapping,
              license_id, license_sha256

SUBJECT       family, family_instance_id, generator_id, generator_version,
              generator_seed, parameters,
              inputs[] { role: SPECIFICATIONAL|EVIDENTIARY, kind, digest, bytes,
                         retrieved_at, trust: trusted|untrusted_text, scope_ref },
              input_closure_digest, prompt_hash, prompt_policy_hash,
              candidate_sha256, candidate_ref, candidate_bytes_len

ORACLE        provision_id, checker_module, checker_source_hash,
              runtime_hash (transitive import closure + sys.version),
              toolchain_pin { id, sha256, manifest_sha256, container_digest|null,
                              platform_triple, offline_capable },
              execution_isolation ∈ {none,restricted_token,appcontainer,
                                     container,separate_host}   [SIGNED, floors tier]
              executes_candidate_code: bool                     [the Tier-A/B filter]
              argv (list, never a shell string), argv_hash,
              oracle_qa_card_hash            [absent ⇒ reward_eligible false]
              held_out_checker_source_hash,
              held_out_agreement ∈ {AGREE,DISAGREE,NOT_RUN},
              determinism { reruns, all_agree }

TIER          evidence_kind ∈ {FORMAL,CONSTRUCTIVE,COMPUTATIONAL,EMPIRICAL,ADJUDICATED}
              tier ∈ {proof_checker, construction_certificate, exact_symbolic,
                      numeric_symbolic, execution_test, simulation,
                      human_endpoint, wet_lab}
              input_tier_multiset      [carried in full, never min()'d to a scalar]
              specification_tier       [specificational inputs, recorded separately]
              isolation_ceiling
              # NOMINAL, not ordinal. Comparison across evidence_kind is a
              # validation ERROR. No field aggregates across kinds.

VERDICT       verdict ∈ {PASS,FAIL,UNDECIDED,UNVERIFIABLE}
              undecided_reason | unverifiable_reason  [typed enum, never free text]
              execution ∈ {COMPLETED,TIMEOUT,CRASHED,RESOURCE_EXCEEDED,
                           TOOLCHAIN_MISSING,HARNESS_ERROR}
              attribution ∈ {CANDIDATE,HARNESS,ENVIRONMENT}
              objective, incumbent_objective, incumbent_provenance_hash,
              incumbent_source ∈ {published_table, operator_search, none}
              coverage { predicate_exact, search_space_enumerated,
                         enumerated_fraction, stop_reason, guarantee_weakens_above }

RAW OUTPUT    raw_stdout_sha256, raw_stderr_sha256, canonical_sha256,
              artifact_ref [PACK-RELATIVE; absolute paths rejected at admission],
              bytes, model_readout: false [structural: meter hashes the byte stream
                                           before any Python reads it]

ANALYSIS      script_path (pack-relative), script_sha256, argv,
              rerun_cmd_template, deterministic

DENOMINATOR   [MANDATORY, no defaults; missing = hard error; null needs a reason code]
              attempts, group_size, verified_subset_size, oracle_calls_consumed,
              held_out_calls, hits, undecided, unverifiable, parse_failures,
              timeouts, resource_exceeded, distinct_input_closures,
              tokens_in, tokens_out, cache_hit_tokens,
              tasks_proposed, tasks_filtered_out, filter_id, filter_hash,
              filter_is_learned                    [the CURRICULUM denominator]

COST          oracle_ns, cpu_ns, gpu_ns, wall_ns, generated_tokens, human_minutes,
              meter_version, verification_host, generation_host
              [distinct hosts: remote burst nodes NEVER sign]

MODEL         model_ref, provider_id,
              base_weights_digest { alg, value, method }, adapter_digest,
              checkpoint_step, adapter_card_hash, adapter_unverified, trainable,
              declared_context, effective_context_measured, metadata_source{},
              quant, tokenizer_sha256, chat_template_sha256,
              sampling { temperature, top_p, seed, max_new_tokens },
              decode_determinism ∈ {deterministic,seeded_nondeterministic,
                                    nondeterministic},
              prefix_hash, cache_hit_rate_measured

LIFT/SCOPE    lift { mode: fresh|replayed|certified_fast, source_receipt_id,
                     cache_key, saved_oracle_ns, scope_id,
                     certifier_provision_id, certifier_tier,
                     forced_reverify, reverify_matched }
              # A lift transfers COST, never TIER. certified_fast carries the
              # CERTIFIER's tier plus a mandatory does_not_prove code.
              scope { scope_id, bounds, reference_set_version,
                      valid_until_invalidation }

NOVELTY       checked, provision_id, corpus_digest, corpus_asof,
              verdict ∈ {REDISCOVERY, NOT_FOUND_IN_CORPUS, UNKNOWN}
              # "NOVEL" is NOT a legal value. NOT_FOUND_IN_CORPUS names its corpus.
              human_gate { gate_receipt_id, rubric_sha256, judge_key_id,
                           sources_searched, search_date }

DOES_NOT_PROVE [required, non-empty; MECHANICALLY DERIVED floor + free-text additions]
              derived: NOT_PROVES_NOVELTY (novelty.checked false)
                       NOT_PROVES_RESISTANCE_TO_ORACLE_GAMING (held_out NOT_RUN)
                       NOT_PROVES_SAMPLING_PARAMS_HONORED (adapter_unverified)
                       NOT_PROVES_WHICH_WEIGHTS (base_weights_digest null)
                       NOT_PROVES_INDEPENDENT_VERIFICATION (lift.mode != fresh)
                       NOT_PROVES_EXACTNESS_ABOVE(p) (coverage.predicate_exact false)
                       NOT_PROVES_CONTAINMENT (execution_isolation none)
                       NOT_THIRD_PARTY_VERIFIABLE_SIGNATURE (sig_alg hmac)
                       NOT_PROVES_GENERATION_REPRODUCIBILITY (decode nondeterministic)
                       TIER_LIMITED_BY_INPUT (input_tier_multiset)
              always:  NOT_PROVES_PUBLICATION_COMPLETENESS
                       NOT_PROVES_KEY_BEYOND_SHELL_ACCESS_ON_THIS_HOST

INVALIDATION  status ∈ {live,superseded,invalidated,contested},
              reason_code ∈ {CRITERION_AMENDED, REFERENCE_SET_REVISED,
                             PROVISION_UPGRADED, SCOPE_VIOLATED, INPUT_MUTATED,
                             ORACLE_QA_FAILED, EXPLOIT_DISCOVERED,
                             CACHE_DIVERGENCE, KEY_COMPROMISED,
                             THIRD_PARTY_DISPUTE, SCHEMA_MIGRATED},
              invalidated_by[], contested_by[]   [downstream records, never mutate]

PROVENANCE    ledger_seq, prev_receipt_hash (FULL sha256), merkle_root,
              inclusion_proof[], consistency_proof[], sth_ref

SIGNATURE     sig_alg ∈ {ed25519} exportable | {hmac-sha256} local-only,
              key_id, sig, exportable: bool
              signed_over = ["attested_digest"]   [fixed in code per schema version,
                                                   NEVER read from the receipt]

NO trust_score field exists anywhere. Only trust_recompute_cmd.
Negative, null, UNDECIDED, and INCOMPLETE receipts are first class and spendable.
```

**RL extension** (`flywheel.rl-receipt/v2` wraps the above): `advantage_estimator`, `loss_normalizer`, `clip_low/high`, `num_iterations`, `kl_coef`, `reference_policy_hash`, `reference_kl`, `sampling_temperature` (single, per group), `seeds[]`, group `{mean, std, learnable, pass_rate, verified_subset_size, entropy_nats, diversity_canonical}`, per‑rollout `{seed, text_hash, raw_oracle_sha256, verdict, objective, reward, advantage, advantage_recomputed, agreement_delta, held_out_agreement, exploit_triggered, predicted_validity, brier, loss_masked}`, `sampler_trainer_logprob_divergence {mean_abs, max_abs, threshold, within}`, `clip_fraction`, `ratio_p50/p99`, `grad_norm`, `effective_batch_size`, `completion_length_p50/p99`, `reheat {entropy_floor_nats, trip, reset, temperature, self_distill_kl, target_detached: true, collapsed, recovery_receipt_id}`, `arm_id`, `prereg_hash`, `control_arm_completed`, `exclusion_ledger_ref`.

---

## 5. Proof protocol

### Bar 1 — preregistered uplift with intervals, published even if null

**Primary metric: mean normalized objective ratio on sealed held‑out generated instances.** Continuous and nonzero at baseline, so the floor effect that voids a frontier count does not apply. The incumbent comes from **arm G, the operator's own search**, not a published table. Held‑out split is **instance‑level within regime** (primary); parameter‑regime extrapolation is a separate secondary transfer metric. Secondary: valid‑certificate rate, count at or above incumbent (expected zero, reported exploratory), Brier from the `learn` calibration probe. `pass@k` is an exploration diagnostic, never optimized, with its inference spend accounted separately from the stopping‑rule budget. No success metric is defined on any family where arm D scores zero, and the base‑rate survey measures the **primary statistic**, not validity rate.

**Arms** (≥3 training seeds for A, B, C, E, F; seed‑level spread is the **primary** uncertainty, task bootstrap secondary; matched on **generated tokens and gradient steps and learnable groups**, with oracle calls reported separately as the economic denominator):

| | Arm | What it rules out |
|---|---|---|
| A | Oracle‑reward RL | — |
| B | Random reward, Bernoulli matched **per step** to A's realized trajectory, with A's difficulty‑band schedule replayed so only the reward varies | spurious‑reward / model‑family artifact |
| C | Shuffled oracle: rewards permuted within family, marginal preserved, pairing destroyed | signal vs. any spread |
| D | Frozen base, identical inference and oracle budget (+ **D_E**, a frozen non‑Qwen base) | trained‑vs‑one‑sample unfairness |
| E | Non‑Qwen base replication on A settings | model‑family artifact |
| F | **Rejection‑sampling SFT** on `developmental.curate()` output at matched oracle calls and tokens | "GRPO beats simply fine‑tuning on the same verified data" |
| G | **Classical search baseline** at equal wall clock | relevance |
| H | **Memorization probe**: verbatim / edit‑distance‑ε overlap against the registry | pretraining contamination |
| — | Compute‑matched inference contrast: post‑RL greedy vs pre‑RL best‑of‑N at equal sampling budget | wrapper uplift vs training uplift |

**Claim rule, frozen before the first scored run.** Uplift is claimed only if **all five** hold: A−D excludes zero, A−B excludes zero, A−C excludes zero, A−F excludes zero, and arm E reproduces the sign of A−D_E. Arms G and H are **reporting obligations, not claim conditions**: if a 200‑line annealer beats the 14B, the uplift claim can be simultaneously valid and irrelevant, and both facts publish. Any failure publishes as a null with the same intervals, the same receipts, and the same prereg hash.

### Bar 2 — reproducible by strangers (this is the headline)

Three independently claimable tiers:
- **T0**: Tier‑A offline replay. No GPU, no network, no account, no install beyond a bare python. Re‑derives every `content_digest`, checks every Ed25519 signature with the vendored verifier, checks inclusion **and consistency** proofs against a published STH, re‑runs every certificate checker (data only, no candidate execution), and regenerates the headline table from raw oracle bytes. Bitwise reproducible.
- **T1**: eval replay on any CUDA box using the published adapter, `base_weights_digest`, `tokenizer_sha256`.
- **T2**: full training replay with a hash‑pinned lockfile and container digest. **Explicitly not bitwise reproducible**, stated in `does_not_prove`.

Scored as receipts independently re‑derived over receipts shipped, **itemized by cause**, with the three‑way outcome split so environment divergence never contaminates the repro rate. Contests are counted and published including unresolved ones. CI on three OSes from a clean network‑disabled clone is the **mechanical stranger**, available in week 2 rather than week 13.

### Bar 3 — developmental retention

Probe set = PASS envelopes ≥30 days old that still re‑witness MATCH, evaluated on **isomorphic perturbations as well as originals**; the gap between them separates retained derivation from retained memorization. Controls: untrained checkpoint (drift floor from toolchain change alone, which also audits the pin) and random‑reward‑trained checkpoint (does forgetting track learning or any weight movement). Plus a general‑code forgetting control from `task_curator`'s hard set. **Mechanism, not just measurement**: `kl_coef > 0` with reference‑KL logged per step, and a preregistered replay ratio of curated SFT batches.

### Bar 4 — entropy and diversity

Per‑step mean per‑token entropy **in nats**, canonicalized diversity (not string distinctness), distinct‑solution count under a canonicalizing hash, `pass@k` curve. **The bar is evaluated on the guard‑OFF arm**; measuring a thermostat against its own setpoint is tautological. Guard‑ON reports recovery cost and incident traces. 2×2 with clip‑higher so the reheat effect is marginal‑on‑top rather than confounded. Collapse is an incident with a recovery receipt, never a dropped run.

### Preregistered before the first scored run (hash‑pinned, externally anchored)

1. `criterion_sha256` per family, including generator ids, seed ranges, and the frozen held‑out seed split.
2. The exact primary‑metric normalization expression; secondaries; diagnostics.
3. All arms, including B's matching algorithm and the replayed difficulty‑band schedule.
4. The analysis script, hash‑pinned **against synthetic data with known closed‑form coverage** before any real data exists.
5. Power analysis, minimum detectable effect, and the number of independent instance clusters.
6. The stopping rule as a fixed budget in generated tokens and GPU‑seconds, never "until significant."
7. The claim rule verbatim and the null‑publication commitment.
8. **The compute‑contingency ladder**: which arm is cut first, second, third if the budget does not hold, and the stated consequence of each cut, so a cut is not a researcher degree of freedom.
9. The entropy floor, derived from the OFF arm's measured trajectory and frozen before the ON arm runs.
10. Abort thresholds: sampler‑trainer logprob divergence, exploit‑hit rate, per‑arm unverifiable‑rate tolerance.
11. The multiplicity hierarchy (primary / secondary / exploratory) with a stated correction.
12. The QA gate: Wilson upper bound on false accepts at declared confidence, with required n per mutation class.

---

## 6. Panel fatal flaws this design fixes

| # | Flaw (lens that found it) | Fix in CC‑1 |
|---|---|---|
| 1 | **GRPO groups sampled across nine temperatures including greedy**, so the importance ratio is wrong for every member and the greedy member pays the policy to become deterministic. **[verified]** `_HOT_TEMPS`, `_SEEDS`, `budget_schedule` index 0 = `(0.0, 0)`. *(RL correctness, all three architectures)* | One temperature per group, fresh seeds per step, `budget_schedule` removed from the training path and retained for selection and eval. `sampling_temperature` and `seeds[]` are receipt fields. |
| 2 | **UNVERIFIABLE is unrepresentable**: `OracleResult.passed: bool`, `verdict()→PASS\|FAIL`, `reward = 1.0 if .passed else 0.0`. **[verified]** Every proposal claimed UNVERIFIABLE is first class through an interface that cannot carry it. *(Epistemics, RL, distribution)* | `verdict.py` + Oracle Protocol widening in Phase 0, with `passed` retained as a property that **raises** so all 28 call sites surface at once. |
| 3 | **UNVERIFIABLE excluded from the gradient is a free escape hatch strictly better than failing** — the policy learns to break the verifier. *(RL on COMMONS; epistemics named it ORACLE_DENIAL on ASSAY)* | Four‑way verdict with attribution. UNDECIDED (oracle decided it cannot decide in scope) → advantage 0, loss‑masked, counted. CANDIDATE‑attributable execution failure → FAIL. HARNESS‑attributable → dropped **and logged to the exclusion ledger**. Declared out‑of‑envelope parameters are rejected before dispatch. |
| 4 | **`flywheel verify` is remote code execution aimed at every stranger** — `shell=True`, full inherited environment, no sandbox, and the bundle supplies both the code and the command line. *(Security, verdict: unsound on COMMONS)* | Construction certificates are **data checkers that never execute candidate code**; `executes_candidate_code` is a schema field a stranger filters on; Tier‑A no‑execution is the default; Tier‑B needs an explicit flag plus a named isolate; a CI AST scan forbids `subprocess`/`socket`/`ctypes`/`pickle`/`eval`/`exec` in any checker module. |
| 5 | **Signing key sits inside the blast radius of candidate execution** (`run_env()` hands the full environment to model‑written code). *(Security)* | Env allowlist, argv not shell, sandbox as a separate OS principal, signer in a different process holding the key, remote burst nodes **never sign** (they return raw bytes, re‑verified and signed at home), and the preferred mode signs the periodic Merkle root rather than each receipt inline. |
| 6 | **HMAC default makes third‑party signature verification impossible**, and Ed25519 "when `cryptography` is importable" contradicts stdlib‑only offline verification. *(Distribution, epistemics, security, product, on all three)* | `ed25519_verify.py`, ~130 lines of vendored stdlib RFC 8032 verify‑only. Ed25519 mandatory for anything exportable; HMAC local‑only and stripped at pack time. `keys.json` with validity windows and revocation ships inside the bundle. |
| 7 | **The verdict is outside the content preimage and outside the signature** — flipping FAIL to PASS breaks no hash. *(Epistemics on ASSAY)* | Two digests: `content_digest` includes the verdict and is what a stranger re‑derives; `attested_digest` covers the full body and is what is signed; `signed_over` is fixed in code per schema version, never read from the receipt. |
| 8 | **Advantage agreement is arithmetically guaranteed to fail or be theatre** (`(r−mean)/std` versus Dr.GRPO's `r−mean`). **[verified]** *(RL, epistemics, maintainability, all three)* | `advantages.py` with an explicit estimator mode set from the same config the trainer uses; a mismatch is a startup error, not a tolerance. `rollout_audit.py` compares the **actual tensor consumed**, not a re‑derivation. |
| 9 | **The receipt is not on the accept path** — the assertion fires after the weights moved. *(Epistemics on CERT‑1)* | `train/reward_gate.py`: write, sign, chain, commit, and only then return the reward. Commit failure returns the UNDECIDED sentinel, so an unreceipted rollout cannot contribute gradient. |
| 10 | **The base‑rate gate measures validity while the primary metric measures the published frontier**, so the exclusion rule voids every family. *(Epistemics on CERT‑1)* | Primary metric is a continuous normalized objective ratio, nonzero at baseline; the base‑rate survey measures the primary statistic; at‑or‑above‑incumbent is a secondary expected to be zero. |
| 11 | **No decontamination control** on families whose answers are published tables. *(RL, epistemics)* | Parameterized generators in unpublished parameter space, incumbents from the operator's own search (arm G), and arm H as a preregistered memorization probe with an edit‑distance check against the registry. |
| 12 | **No rejection‑sampling SFT baseline**, though `developmental.curate()` and `qlora_cpt.py` already build it. *(RL on CERT‑1 and COMMONS)* | Arm F, and it is a claim condition, not an optional extra. |
| 13 | **Task‑bootstrap CIs on single training runs, clustered over three families**, presented as intervals on the treatment effect. *(RL)* | `uplift_stats.py`: ≥3 seeds, seed spread primary, cluster resampling over (instance, seed), permutation test over seed×arm, preregistered power analysis and MDE. `forecast_bootstrap.py` is a pass@k forecaster and is not used for this. |
| 14 | **Tier as a total order with `min()` puts human judgment and measurement at the bottom**, so every human‑posed conjecture floors there and the incentive is to prune the input closure. *(Epistemics on ASSAY)* | `evidence_kind` is **nominal**; comparison across kinds is a validation error; specificational inputs are recorded separately and do not floor the claim; the input tier multiset is carried in full. |
| 15 | **`certified_fast` launders tier** — the certifier's tier never enters the floor. *(Epistemics on ASSAY)* | A lift transfers cost, never tier. `certified_fast` carries the certifier's tier plus a mandatory `does_not_prove` code; only an epsilon‑reverified instance may carry the slow oracle's tier. |
| 16 | **No criterion object anywhere in ASSAY's schema**, so a post‑hoc criterion edit is indistinguishable from a bug fix and no third party can accept the evidence while rejecting the criterion. *(Epistemics)* | `criteria/spec.py` is a first‑class hash‑pinned receipt field with `CRITERION_AMENDED` invalidation, and `criteria/` ships in the pack so a fork substitutes a criterion and re‑derives verdicts against the same replay artifacts. |
| 17 | **Vote aggregators are structurally admissible as reward oracles** (`ACCEPT_VERDICTS` includes `CONSENSUS_PASS`; `ConsensusOracle` has majority and weighted rules). *(Epistemics)* | Registry admission refuses non‑conjunctive decision rules for reward eligibility; `CONSENSUS_PASS` maps to UNDECIDED at mint time; composed provisions must enumerate their members. |
| 18 | **No inbound refutation channel** — the party being refuted decides which refutations get recorded. *(Epistemics)* | `contest.py` plus counter‑receipts signed with the contester's own key; open‑contest count and time‑to‑resolution are published series; Bar 2 scores contests. |
| 19 | **Inclusion proofs with no consistency proofs and no external anchor**, so split‑view is undetectable and append‑only is policy. *(Epistemics, security)* | RFC 6962 consistency proofs, signed tree heads, external anchoring, full‑sha256 chain links (the current 64‑bit truncation is ~2^32 birthday work). |
| 20 | **Zero product surface across all three; the desktop hero is unfunded for a quarter and would render v2 receipts with the honesty fields invisible.** *(Product)* | `why.py` plus a Phase‑1 desktop receipt‑v2 renderer, `does_not_prove` **mechanically derived and rendered**, the fourth verdict as a word and a shape, the three‑way verify outcome, and a budget the human holds (estimate, cap that halts, live meter, cancel that still emits a receipt). |
| 21 | **No CI, red suite, unenforced 300‑line gate, 16% orphan modules.** *(Maintainability)* | CI is milestone 0; a milestone completes when something is reachable from `flywheel` and covered end‑to‑end, not when a file exists; the orphan check blocks new dead modules. |
| 22 | **FSL‑1.1‑MIT contradicts "cannot be relocked" and blocks both hubs.** *(Distribution)* | License split decided in Phase 0 and written into the criterion and the receipt: Apache‑2.0 for harness, criteria, checkers, verifier, bundles, adapters; FSL retained only where it is not load‑bearing for verification. |

---

## 7. Residual risks and honest unknowns

1. **Elicitation versus expansion stays unresolved, and this design makes it sharper, not softer.** Choosing generated families where the base is nonzero is what makes the metric measurable, and it is also the exact regime where sharpening and expansion are hardest to separate. The compute‑matched inference contrast is the only available lever, and it is a diagnostic, not an answer.
2. **The classical search baseline may simply win.** For Zarankiewicz and constant‑weight codes, a small annealer at equal wall clock is a live threat. A valid uplift claim and an irrelevant one are compatible, and both publish.
3. **A five‑condition conjunction at three seeds has low power.** The preregistered MDE will say so before the run. A wide null is the modal outcome and is the honest price.
4. **Key custody is policy, not architecture, on a single‑operator box.** Separate principal plus offline root signing shrinks the window; root on this host still defeats it. It says so on every receipt and every surface.
5. **Named invalidation has no principled setting.** Over‑invalidate and the amortization dies; under‑invalidate and stale receipts earn credit. Only the drill and measured divergence inform it.
6. **Verifier QA bounds only the mutations we imagined.** The Wilson bound quantifies the sample, not the imagination. The exploit catalog is candidate‑side and still finite.
7. **Bar 2's human evidence cannot be self‑generated.** CI is a mechanical stranger, not a real one. Thin volunteer turnout leaves the strongest bar weakly evidenced no matter how good the engineering.
8. **Construction certificates generalize weakly.** A positive result transfers poorly to the tasks most people care about, and a reader can fairly ask whether it transfers at all.
9. **Cross‑fork reconciliation is unsolved.** Criteria fork and receipts stay schema‑comparable, but nothing defines how two forks' version namespaces reconcile or how a reader determines which fork a headline used.
10. **Windows toolchain.** The bitsandbytes plus gradient‑checkpointing deadlock is a recorded scar; TRL + vLLM + Unsloth is a worse surface. WSL2/Linux is pre‑booked as Phase‑1 scope, not a contingency, and the environment digest forks across two environments so training and verification cost samples are not directly comparable.
11. **Selective publication.** Append‑only plus external anchoring makes rollback detectable; it does not make non‑publication detectable. `NOT_PROVES_PUBLICATION_COMPLETENESS` is on every receipt and no design choice removes it.
12. **Six modules are estimated at 230 to 280 lines.** At least two of those estimates are wrong on the low side and will become packages. `receipt.py` and `oracle_qa.py` are the likeliest.

---

## 8. Milestone plan

### Phase 0 — Ground (weeks 1 to 2). Nothing new until the floor holds.
CI matrix with the clean‑clone network‑disabled verify job, the stdlib import‑graph assertion, the gate burn‑down, the orphan check, and the no‑execution AST scan. Green the suite; move filesystem‑state assertions behind a marker. License split written. `verdict.py`, the Oracle Protocol widening, `run_env` allowlist, argv not shell, `start_new_session`, rlimits. Gateway token, Host allowlist, Content‑Type. **Gate:** take one existing orphan chain fully end to end (`matmul_oracle` → `rl_from_oracle.collect` → receipt → verify → MATCH) behind one command with an acceptance test, using only code that already exists. If that cannot be done in one week, the plan is disproven cheaply and early.

### Phase 1 — First proof (weeks 3 to 8). The spine that survives a null.
Criteria spec and registry. Two certificate families plus generators, independent checkers, and the matmul adapter. `oracle_qa` with planted exploits and Wilson bounds; the QA gate goes live and any family that cannot clear it is cut. Receipt, signing, vendored Ed25519, ledger, bundle, verify, contest. `why` plus the desktop receipt‑v2 renderer and the budget surface. **Base‑rate survey on the primary statistic**; families that fail are cut *before* preregistration. Prereg, control arms, `uplift_stats` validated on synthetic data, analysis script hash‑pinned and externally anchored. Reward gate, TRL optimizer, rollout audit, entropy guard, search baseline. **7B pilot: arms A, B, D, G, H, three seeds**, published as a dress rehearsal for the analysis pipeline and explicitly not the uplift claim. **First stranger trial in week 4** on one certificate bundle, not week 13.

### Phase 2 — Hardening (weeks 9 to 11).
Families 3 and 4. Cost meter and amortize with the replay/transfer split and epsilon‑rate forced re‑verification; run the **invalidation drill** (mutate an upstream input, confirm downstream invalidation, confirm cost recomputes *upward*, confirm nothing was rewritten). Adapter layer: discovery, negotiation, prompt cache, toolcall, adapter card, with six heterogeneous backends carded including at least one where measured context differs from declared and the difference is recorded. **Main run: 14B, arms A, B, C, D(+D_E), E, F, three seeds, bursting to rented CUDA**, with remote nodes producing unsigned receipts that are re‑verified and signed at home. Retention probe with isomorphic perturbations. Entropy guard ON/OFF ablation.

### Phase 3 — World distribution (weeks 12 to 13).
Bundle hardening (zip‑slip, symlinks, absolute paths, size budget, secret scan hard‑fail) and the Pack/Env split with hidden tests as salted commitments. STH publication to an external anchor; key rotation and revocation. `envs/flywheel_certificates` into `verifiers` and OpenEnv, pinned to named upstream commits, on their own process. `reproduce.ps1`/`.sh`. PyPI under a checked name with the import package renamed off `harness`. **Publish**: prereg hash, all receipts, adapters, replay bundle, the four‑bar table with intervals **including the null**, every DRIFT with its typed cause, every contest including unresolved ones.

### Deliberately NOT built yet

- **No instance proposer.** Generators with a difficulty knob only. This gives up the largest amortization win in the corpus in exchange for a fixed, enumerable instance set a stranger can regenerate from a seed.
- **No Lean 4 / Mathlib tier.** The `proof_checker` slot is declared and empty. Three reasons: a multi‑gigabyte olean cache breaks the offline claim; Lean elaboration executes arbitrary code (`#eval`, `native_decide`, `@[extern]`), making it a second unsandboxed execution surface dressed as the most trustworthy tier; and admitting it without axiom‑footprint auditing, `sorry` screening, `native_decide` demotion, and statement‑hash binding certifies nothing. `harness/lean_oracle.py` already does the audit correctly, and it gets promoted when Phase‑3 isolation and a per‑platform sidecar pin exist.
- **No allocator or price mechanism.** Cost is metered and budgeted; it is not optimized. An objective of receipts per oracle‑second structurally favors cheap tiers and drives the curriculum out of the learnable band, and its quota floor is a hand‑set parameter with no principled value.
- **No falling‑marginal‑cost headline.** The transfer series is a Phase‑3‑plus result on novel input closures with dispositive verdicts only; the replay series publishes separately as an engineering fact carrying no claim.
- **No consensus or quorum anywhere near reward.**
- **No calibration reward term.** Brier is a receipt field and a Bar‑1 secondary. As an additive reward component it has a degenerate optimum (predict 0.0, emit garbage); the multiplicatively gated form needs its own ablation first.
- **No hosted‑provider training.** Hosted endpoints are `evaluatable_only`; the portability promise covers evaluation, not gradient, and the AdapterCard says so.
- **No zkML** (10^4 to 10^5 slower) and **no TEEs** (someone else's hardware).
- **No trust score, ever.**

---

### Where the panel disagreed, and the ruling

**Headline metric.** Uplift is Bar 1, preregistered and published including the null, but it is **not** the headline. The headline is Bar 2: offline stranger re‑derivation of a criterion‑pinned corpus. It cannot be a model‑family artifact, it is immune to the elicitation confound, and it lands on a named gap nobody ships. Cost is an instrument and a user budget, not a headline, because the oracle call is not the scarce resource for a millisecond stdlib checker and a frozen‑mix replay series falls by construction.

**Build order.** Seams first, then environment, then trainer, with the trainer inside the window. ASSAY's seventy days before the first gradient is rejected because the gradient seam is the untested part. CERT‑1's trainer in week three is rejected because the Protocol widening and the on‑path receipt must precede it or both invariants are decorative.

**Scope.** Two certificate families in Phase 1, four total, matmul wrapped rather than rewritten, Lean deferred. A null on two well‑generated families with clean QA is worth more than a null on five rushed ones.

**Adapter layer.** Built in full, in Phase 2. CERT‑1's "defer past day 90" is rejected because the requirement is binding; COMMONS's six‑backend target is kept, but determinism is graded three‑valued and `adapter_unverified` receipts run while staying inadmissible to the science.