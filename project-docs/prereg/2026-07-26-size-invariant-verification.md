# Preregistration: size-invariant verification

**Status:** FROZEN on the date this file's sha256 is appended to the ledger and
git-tagged. Nothing scored runs before that. A run executed before the freeze
permanently weakens the record and cannot be retrofitted, which is the entire
reason this document exists.

**Prereg id:** `prereg.size-invariant-verification.v1`
**Author:** the operator, one maintainer, one 24 GB consumer GPU.
**Register:** internal. This document is the commitment; the published page is
downstream of it.

---

## 0. What is being claimed, in one paragraph, before any detail

The accept path is a pure function of the criterion hash and the certificate
bytes. It never receives model identity, never executes candidate code, and
therefore returns byte-identical verdict digests for identical certificate bytes
regardless of which model, size, family, backend, or quantization produced them.

**That claim is near-tautological and a reader who says so is right.** It is a
design property, not a discovery. It is preregistered anyway, because the
alternative is discovering a bug in it after building a training run on top of it,
and because the artifacts shipped alongside it are the actual substance: four-way
outcome tables with UNDECIDED and UNVERIFIABLE in the denominator, a pinned
inference fingerprint, QA cards with per-class Wilson bounds, an append-only
ledger with consistency proofs, and a bundle that verifies offline with no network
and no GPU.

The limitation goes in the first paragraph of any public page, not the last.

## 1. The words that may not be used

Frozen vocabulary, because the wrong phrase makes a claim we are not making.

| Forbidden | Required instead | Why |
|---|---|---|
| "the environment scales" | "size-invariant verification" | RLVE (`arXiv:2511.07317`) already owns "environment scaling" for scaling the NUMBER of environments, and reports it as a capability gain. Readers will hear that claim |
| "uplift", for any inference-time arm difference | "verified pass@k" | The quantity is a sampling-budget effect. Uplift is reserved for a trained-policy comparison that does not exist yet |
| "the rectilinear crossing number of G" | "the crossing count of the submitted drawing" | See section 8. This one is the most likely to be lost in retelling and now has a CI gate |
| "the Zarankiewicz number z(m,n;2,2)" | "a verified K_{2,2}-free graph with N edges" | Same failure, same reason |
| "optimal", "minimum", "best possible", of any candidate | "the best VERIFIED value we have seen" | No checker in this repository decides optimality |

## 2. Instruments, pinned by hash

Two construction-certificate families. Both have a genuinely independent second
checker, which is a hard requirement: an arm whose selector is the same function
that scores it cannot lose, so without a held-out scorer no selection comparison
is two-sided and the measurement is a tautology with a number attached.

### Criteria

| criterion_id | criterion_sha256 | direction |
|---|---|---|
| `zarankiewicz.z_2_2.v1` | `sha256:005c78ef74971a29ff46e15bc6fe60eecb8840344243f2a3d8ac1e9e03a1fe38` | maximize edges |
| `rectilinear_crossing.count.v1` | `sha256:8da711d840c82ce0789da701e962bdd6dcd8d77290efef96c28bf522d9edbe8d` | minimize crossing pairs |

### Checkers, by source digest

| role | class | source_sha256 |
|---|---|---|
| zarankiewicz primary | `ZarankiewiczOracle` | `48dd8fc79cb8ac98fa6fe20d373f80027bddac007f3fd169ccc06164d7ac4e7b` |
| zarankiewicz held out | `IndependentZarankiewiczOracle` | `5bbc45082233037bc972c4d19fbc21e5ecb1bdbabc56637dcb164c332ace8bca` |
| crossing primary | `CrossingOracle` | `95720ae127e5f3b4e733c2b89afef5239b9db5c01a1b8f21eddfce6ebfb1b620` |
| crossing held out | `IndependentCrossingOracle` | `d1106354526e97e08c5eaecb09dd9d3a517e2eec0a59533e024b6a55ff9d63b5` |

Any edit to a checker changes its digest and invalidates this prereg for that
family. That is the intended behaviour.

### Generators

`zarankiewicz.bipartite.v1` v1, and `crossing.random_nonplanar.v1` v1. Both
exclude the parameter regions with published answers: `EXCLUDED_PAIRS` covers the
small square z(m,n;2,2) cases, and the crossing generator never emits a complete
graph, because rectilinear crossing numbers of K_n are published for small n.

### Instances

**60 instances per family**, difficulties 1 through 5, twelve per band.
**Seeds are the explicit list 0 through 59**, assigned to bands in blocks of
twelve in ascending order. This list is frozen. It is written out rather than
described as a range, so a later run cannot quietly widen it.

## 3. The ladder

Nine submission contexts. One engine, one quantization, one fingerprint held
identical across rungs.

**All nine rungs are pinned.** Pinning does not require possession: the Ollama
registry is content-addressed, so a manifest digest identifies a model exactly and
anyone can verify it without downloading. `ollama pull` verifies against these
same digests, which makes the pin a check on acquisition rather than a promise
about it.

Locally present, pinned by the blob digest of the served model:

| rung | model | blob digest |
|---|---|---|
| R1 | `qwen2.5:0.5b` | `sha256-c5396e06af294bd101b30dce59131a76d2b773e76950acc870eda801d3ab0515` |
| R2 | `qwen2.5:3b` | `sha256-5ee4f07cdb9beadbbb293e85803c569b01bd37ed059d2715faa7bb405f31caa6` |
| R3 | `qwen2.5:7b` | `sha256-2bada8a7450677000f678be90653b85d364de7db25eb5ea54136ada5f3933730` |
| R4 | `telos-coder-14b` (cpt2020) | `sha256-613db240e3efc6730f24042a4602d1f12f1c6b397af1d5a4d74f4e064d4064be` |

R4's blob digest is byte-identical to the GGUF sha256 on its public model card,
which closes that provenance chain.

Not yet served, pinned by upstream manifest and model-layer digest:

| rung | model | manifest sha256 | model layer | size |
|---|---|---|---|---|
| R5 | `qwen2.5-coder:14b-instruct-q4_K_M` base control for R4 | `9ec8897f747e246e970bc5cfdda85d22f1123dc2e3d34978a010a75968716849` | `sha256:ac9bc7a69dab38da1c790838955f1293420b55ab555ef6b4615efa1c1507b1ed` | 8.37 GiB |
| R7 | `qwen2.5-coder:32b-instruct-q4_K_M` base control for R6 | `b92d6a0bd47ee79114298de0177bf920c05a706d12633950b3936778492bef41` | `sha256:ac3d1ba8aa77755dab3806d9024e9c385ea0d5b412d6bdf9157f8a4a7e9fc0d9` | 18.49 GiB |
| R8 | `olmo2:7b`, the non-Qwen rung | `4208d3b406db076e1569c97a2fb67cf9c86b845544c1a61ff218259daf9e3538` | `sha256:ea89e3927d5ef671159a1359a22cdd418856c4baa2098e665f1c6eed59973968` | 4.16 GiB |
| R9 | `qwen2.5:1.5b` | `65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b` | `sha256:183715c435899236895da3869489cc30ac241476b4971a20285b1a462818a5b4` | 0.92 GiB |

Local artifact, pinned by weight digest, verified rather than trusted:

| rung | model | weight sha256 | bytes |
|---|---|---|---|
| R6 | `telos-coder-32b` cpt2019 q4_K_M | `65e6133fbe4d12579a776047a71bebb98ab86f9e3d343ed821b51dac0ce312f4` | 19,851,336,480 |

R6's digest was recomputed from the file on 2026-07-26 and matched the value
declared in `harness/model_profiles.py`. **R6 is pinned but not yet servable**: it
is not registered in Ollama, and registering it copies 18.5 GiB into the blob
store. Pinned and servable are different states and this document keeps them
apart, because a rung can be identified without being runnable.

**R8 is `olmo2:7b` and there is no alternate.** OLMo 2 is chosen over Llama 3.1
because its data and training code are open as well as its weights, which makes it
the better scientific control. `llama3.1:8b` is recorded here as pinned
(`46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e`) so that a
later substitution is traceable, and substitution is NOT permitted inside this
prereg: if OLMo 2 fails to load or serve at the declared context, the run aborts
and is logged, and any substitution requires a new prereg citing the aborted one.
A pre-approved alternate is a degree of freedom, which is the thing this document
exists to remove.

**Two acquisition constraints, recorded so they cannot surface as surprises.**
Ollama's blob store is on the system drive with roughly 72 GB free; R5, R7, R8 and
R9 together are about 32 GiB, which leaves the drive uncomfortably full, so the
store may need relocating to the run drive first. And R7 at 18.49 GiB of weights
on a 24 GB card leaves roughly 5.5 GB for KV cache and overhead; if it spills to
CPU offload the declared fallback is to ship the eight-rung ladder with R7 marked
pending rather than let one rung hold the artifact.

**Correction carried forward:** the installed small models are the general
`qwen2.5` line, while the trained artifacts are `qwen2.5-Coder`. The existing
"ladder" in the old artifacts is therefore two families, not one. Any rate
reported across R1 to R4 inherits that confound and must say so inline.

**R8 is load-bearing, not a spot check.** A preregistered causal partition
(`arXiv:2606.05932`) reports elicitation at 0.98 of gains for strong-prior Qwen
models with the ordering reversed for Llama and OLMo, and Spurious Rewards
(`arXiv:2506.10947`) reports random reward buying +21.4pp on Qwen2.5-Math-7B while
largely failing on Llama3 and OLMo2. Everything trained here is Qwen. So our
family is the one where reward design is reported to buy least and a
zero-information reward buys most. R8 is the only rung that could tell us whether
we measured the environment or measured Qwen. At n=1 it still supports no
generality claim.

## 4. Arms, all offline from one cached pool

Generation is decoupled from selection. `harness/pool.py` caches **K = 4**
candidates per instance per rung with **no early stopping**, content-addressed,
each slot recording seed, temperature, model digest, engine, engine version and
quantization. Every arm below is then a pure function of that cache, so a stranger
recomputes the entire analysis on a laptop with no GPU and no network.

Fingerprint fields, all of them recorded, absent values recorded as null rather
than omitted: `model_ref, model_digest, engine, engine_version, quantization, k,
seeds, temperatures, max_new_tokens, prompt_template_sha256`.

| arm | selector | scored by | comparable? |
|---|---|---|---|
| `single` | none, slot 0 at temperature 0 | oracle | baseline |
| `best_of_k`, self-scored | oracle | itself | **NO. Reported as verified pass@k with no p-value** |
| `best_of_k`, held out | primary checker | the independent checker | **YES** |
| `random_of_k` | seeded coin | oracle | yes, against the held-out arm |
| `placebo_of_k` | acceptor matched on the oracle's accept rate, zero ground truth | oracle | yes |
| `pass_at_k` to K=4 | diagnostic | oracle | no claim attached |

`paired()` refuses a two-sided statistic for any arm marked `scored_by
= "selector"`. This is enforced in code, not in this document.

**Frozen now, before the trainer exists, so it cannot be dropped later when it
is inconvenient:** any future training run under verified reward must carry a
**random-reward arm** and a **format-only-reward arm**. On a Qwen-only stack a
positive result without them is uninterpretable, because the literature's null
hypothesis for this exact family predicts a large positive effect from a reward
with no information in it.

## 5. Endpoints

**Primary endpoint: a count, with no rate in it.**

> N distinct certificate bodies, submitted through the accept path once per rung
> context, yields N distinct verdict digests and zero disagreements.

The unit of observation is the **certificate body, not the model**. Permuting
model-identity fields would assert only that a pure function ignores an input it
does not take. Instead: take the union of all bodies produced by all rungs, submit
each through the accept path in every rung context, and assert one verdict digest
and one receipt subject digest per body, with divergence permitted only in the
receipt fields that record provenance.

**Secondary endpoints, per rung, reported and never compared across rungs:**
well-formedness rate, the four-way verdict distribution, and the CANDIDATE /
HARNESS / ENVIRONMENT attribution split. Ordered by rung id, never by size. No
cross-rung delta is computed. The confounds are listed inline with every table:
the 8x token asymmetry, the 8x training-context asymmetry, Qwen-only, one
backend, and one quantization.

**Denominator: all four verdicts, always.** PASS, FAIL, UNDECIDED, UNVERIFIABLE.
A task with no candidate in any slot is excluded and reported separately, because
grading a task nothing was generated for attributes a harness gap to the
candidate.

## 6. Statistics and the declared MDE

- **Primary variance component is between-seed.** An SD from r = 3 full pipeline
  replicates minimum, 5 preferred. Never a range presented as an SD: E[range] at
  n=2 is 1.128 sigma, so a 2.7pp two-run spread implies sigma near 2.4pp, not
  1.35pp.
- **Task-population standard errors clustered** by difficulty band and generator
  seed, because the generator emits related groups and unclustered SEs are
  anticonservative.
- **Intervals by hierarchical bootstrap**, seed as the outer resample and instance
  as the inner, so the primary component dominates the width.
- **Primary test for any paired comparison: McNemar exact on discordant pairs**,
  and it may not be run until the determinism receipt shows the shared-generation
  invariant holds.
- **Declared MDE, published next to every result including every null.** Present
  single-run resolution on the old 110-task instrument was plus or minus 12.8pp
  against a 15.45pp point estimate, measured. With arms sharing a cached pool the
  binding quantity becomes the discordant-pair count and n falls sharply. Both
  numbers get published. Without an MDE, "no effect" and "no power" are
  indistinguishable to a reader.

## 7. Stopping rule and claim rule

**Stopping rule.** Fixed instance set, fixed K, fixed seed list, one confirmatory
run. No interim analysis. No peeking at outcomes. No extension on an unfavourable
result. A run aborted for a mechanical reason is logged with its reason, and the
rerun is a NEW prereg hash that cites the aborted one. Selection by newest mtime
is deleted from `uplift_bench.py` and `frontier.py`; the confirmatory run is named
by hash.

**Claim rule.**

| Observed | Permitted statement |
|---|---|
| Zero verdict-digest disagreements across all contexts | "Verification is identical at every model size and family tested, for these two oracle families, one backend, one quantization." Nothing about capability |
| Any disagreement, any body | **The claim has failed.** Publish the failure, the body, both digests, and the located divergence. Do not re-run to make it go away |
| Well-formedness near zero at small rungs | Report as expected. It is a property of the proposer, not of the environment |
| Any cross-rung rate difference | **Unclaimable.** Confounded by tokens, context, family, backend |
| Any inference-time arm difference | Reportable only as verified pass@k against the compute-matched oracle-free arm and the placebo, with McNemar and the MDE, and never as uplift |
| A held-out best-of-k arm beating random-of-k | The strongest available statement, and still only about SELECTION, never about the model having learned anything |

**Modal outcome, stated in advance so a boring result cannot be spun as a
surprise.** Invariance holds; it is a pure function of data, so the informative
result would be a bug. Well-formedness is near zero at 0.5B, single digits at 3B
and 7B, low double digits at 14B. Base and CPT rungs are indistinguishable within
the seed-level SD. The honest headline is: verification is identical everywhere,
capability is not measured, and this says nothing about whether the environment is
useful for training.

## 8. The distinction that must not be lost in the retelling

**Every checker here verifies a submitted object. None decides optimality.**

- The crossing checker verifies the crossing count OF THE SUBMITTED DRAWING. The
  rectilinear crossing number of the graph is not computed, not bounded above, and
  not claimed.
- The Zarankiewicz checker verifies K_{2,2}-freeness and the edge count OF THE
  SUBMITTED GRAPH. The Zarankiewicz number is not claimed.
- The matmul checker verifies that a submitted scheme computes the product
  exactly. It does not claim the rank is minimal.

This is the single most likely thing to be lost when a result is retold, because
"our model found a drawing with 103 crossings" compresses naturally and wrongly
into "our model found the crossing number". Three mechanisms, because a note in a
document is not a mechanism:

1. **Every result carries it.** `NOT_PROVES_OPTIMALITY` travels in
   `does_not_prove` on every crossing and Zarankiewicz result, into every receipt,
   into every bundle.
2. **A CI gate scans the public surfaces.** `scripts/check_claim_language.py`
   fails the build on optimality language near these families on any shipped
   page. The gate, not the reviewer, is what holds.
3. **The objective is reported next to the verdict, never instead of it.** A
   number without its verdict and denominator is the fake-passport failure: true,
   and useful for implying more than it establishes.

## 9. What is deliberately not built, stated as a choice

Any RL training under verified reward: `PolicyOptimizer` stays an unimplemented
Protocol. `harness/prereg.py`, because preregistration derives its force from a
hash committed before the run and not from a Python API. Any pass@k inversion
program, any position on elicitation versus expansion, and any sigmoidal
compute-performance fit. That last one is **structural, not a backlog item**: the
smallest published RL scaling ablation spent up to 16,000 datacenter GPU-hours per
point with fitting beginning after roughly 1,500, against on the order of 8,760
much weaker hours per year on one 24 GB card. Say so in writing.

## 10. Freeze record

To be completed at freeze, and this document is not frozen until they are:

- [ ] sha256 of this file, computed on the committed bytes
- [ ] ledger entry appended, with its inclusion proof
- [ ] signed tree head over the ledger at that size
- [ ] git tag `prereg/size-invariant-verification-v1`

Contamination posture at freeze, established and recorded separately in
`project-docs/records/2026-07-26-corpus-timeline.md`: one pack exists on the run
drive, sealed 2026-07-03 02:10, which predates `hard_v2.jsonl` (2026-07-06
23:08:51) and `HumanEval.jsonl.gz` (2026-07-09 23:01). Both CPT runs read it
because there is nothing else to read. Neither evaluation set existed as a file
when the corpus was packed, and that bound covers the 32B as well as the 14B. It
rests on filesystem timestamps, which are evidence and not proof, and it does not
bound overlapping content inside the 17,997 packed source files. The enumerated
manifest stays required for any claim that needs that stronger bound.

**Both instrument families are contamination-clean by a stronger argument than
ordering:** every file in `harness/certificates/` was first admitted 2026-07-25 or
later, and both CPT runs completed before it existed. The Zarankiewicz and
crossing families therefore cannot be in either training corpus, and that holds
without needing the pack manifest at all.
