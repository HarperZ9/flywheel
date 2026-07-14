# Compute frontier: domain dossier (2026-07-14)

Method: every finding below was adversarially re-checked against a live fetch
of its source; claim text was matched to the source's own words and numbers.
Six findings survived checking, eight failed and were dropped. Nulls are
first-class content here.

## 1. The frontier in five sentences

Single-user local inference in mid-2026 is decode-bandwidth-bound: two boxes
with a 2x gap in achieved compute (101 vs 46 BF16 TFLOPS, high confidence)
generate tokens at nearly the same pace because they sit at 273 vs 256 GB/s of
memory bandwidth (theregister.com, 2025-12-25). The standard escape hatches
are all real but all conditional: 4-bit weight quantization loses up to 59% on
long-context tasks that short-context benchmarks miss entirely
(https://arxiv.org/abs/2505.20276, v3 2025-09-20), the lossless KV-cache
quantization floor moves between 3.25 and 4.0 bits across two same-scale
models (https://arxiv.org/abs/2502.04420, ICML 2025), and speculative
decoding's best published consumer result (3.2x on Apple Silicon,
hiesch.eu, 2026-05-06) is a favorable MoE-target case, not a floor.
Meanwhile the hosted side is not standing still: the price to reach a fixed
capability on hosted APIs fell 9x to 900x per year depending on benchmark,
median 50x (epoch.ai, 2025-03-12), so any local-vs-hosted cost claim decays
within months. Nobody has published a measured, apples-to-apples batch-1
$/token comparison at matched quality; every comparison found either assumes
datacenter utilization or quotes batch-128 efficiency a local box cannot
reach. That missing measurement, and the per-model conditionality of every
optimization above, is exactly the shape of work a verified-inference
platform exists to produce: dated receipts instead of extrapolated claims.

## 2. Confirmed findings

### F1. 4-bit weight quantization fails long-context evaluation, model-dependently

Claim: 8-bit weight quantization preserves accuracy (~0.8% drop, high
confidence) while 4-bit methods lose up to 59% on long-context tasks (high
confidence); the damage is model-family-specific: Qwen-2.5 72B stays robust
under BNB-nf4 while Llama-3.1 70B drops 32% under the same quant (high
confidence). Measured across 9.7K examples on Llama-3.1 8B/70B and Qwen-2.5
7B/32B/72B.

Source: https://arxiv.org/abs/2505.20276 (v3, 2025-09-20; EMNLP 2025).
Abstract states all figures verbatim.

Why it matters: this repo ships GGUF artifacts, and the default publishing
practice everywhere is to validate quants on perplexity and MMLU-style
benchmarks, which this paper shows can miss a 59% long-context regression
completely. A verified-inference platform cannot publish a quant artifact
whose verification harness is blind to the failure mode.

Pour-back: the model release checklist
(`project-docs/release/MODEL-RELEASE-READINESS-14B-32B-2026-07-08.md`) and
the bench harness. Shape: a long-context eval gate that must run per quant
artifact before publish, with the per-quant delta recorded as a receipt.

### F2. Lossless KV-cache quantization floors are per-model, not universal

Claim: KVTuner reaches nearly lossless 3.25-bit layer-wise mixed-precision KV
cache quantization for Llama-3.1-8B-Instruct but needs 4.0-bit for
Qwen2.5-7B-Instruct on math reasoning (both high confidence), with up to
21.25% throughput gain over KIVI-KV8 (high confidence).

Source: https://arxiv.org/abs/2502.04420 (submitted 2025-02-06, v5
2025-11-20; ICML 2025). Abstract matches all figures.

Why it matters: KV cache is the memory ceiling for long-context batch-1
inference, and the finding kills the idea of one global low-bit KV setting.
The platform's serving configuration needs a per-model profile whose numbers
were measured, not inherited.

Pour-back: serving configuration in `HARNESS.md` and the runtime config.
Shape: a per-model profile field (kv_bits) that is invalid without a pointer
to the measurement that justified it.

### F3. At matched bandwidth, 2x compute buys prefill only

Claim: DGX Spark ($3,999, 273 GB/s) and the HP Z2 Mini G1a Strix Halo
($2,949, 256 GB/s) generate tokens at a similar pace because decode is
bottlenecked by memory bandwidth, while Spark's 101 achieved BF16 TFLOPS
(MAMF-measured) vs 46 gives roughly 2-3x faster time-to-first-token (all
figures high confidence, verified against the article text).

Source: theregister.com, Tobias Mann, 2025-12-25. The exact URL path was not
retained in the verification record (domain and date high confidence, path
unknown).

Why it matters: hardware guidance for local inference is dominated by
compute-spec marketing, and this is a measured counterexample: the $1,050
premium buys prefill speed, not generation speed. A platform that recommends
or benchmarks hardware should key its guidance to memory bandwidth for
decode-bound workloads and say so with the measurement attached.

Pour-back: a dated hardware decision sheet in `docs/research/`, feeding the
backend matrix lane already present under `artifacts/backend_recovery_matrix*`.
Shape: a two-axis table (GB/s for decode, achieved TFLOPS for prefill) where
every cell carries source and date.

### F4. Speculative decoding's best consumer result: 3.2x on an MoE target

Claim: llama-server b9020 on an M3 Max with 64 GB took Gemma 26B-A4B from
63.9 t/s to 206.5 t/s using a 1.6 GB Gemma4-E2B Q4_K_M draft model, a 3.2x
speedup, with memory rising from 22 GB to 31 GB (all figures high confidence,
verified against the page's own table).

Source: hiesch.eu, 2026-05-06. Exact URL path not retained in the
verification record (domain and date high confidence, path unknown).

Why it matters: a 3.2x batch-1 decode gain with no quality loss is the
largest single lever available to a local box, and it costs only memory. But
the null below (N3) shows the gain is content-dependent and can go negative,
so the platform's job is to measure acceptance rate per model pair and ship
the pairing only with its receipt.

Pour-back: serving profile in `HARNESS.md` (same profile object as F2).
Shape: draft_model field plus a measured before/after tokens-per-second pair
on this repo's own task set.

### F5. Backend choice is worth ~2x on identical hardware

Claim: Ollama 0.19's MLX preview on Apple M5 lifted Qwen3.5-35B-A3B prefill
from 1,154 to 1,810 t/s and decode from 58 to 112 t/s versus Ollama 0.18,
with int4 reaching 1,851 t/s prefill and 134 t/s decode (all figures high
confidence, verified against the post). One nuance survives verification: the
0.18 baseline ran Q4_K_M under the prior implementation, not NVFP4, so this
is a backend-plus-format delta, not a pure backend delta.

Source: ollama.com blog, 2026-03-30. Exact post slug not retained in the
verification record (domain and date high confidence, path unknown).

Why it matters: a 2x swing from software alone, on unchanged hardware, means
any benchmark receipt this platform emits is meaningless without backend name
and version pinned in the receipt. It also means backend upgrades are a
recurring free-performance event worth re-measuring on a schedule.

Pour-back: the backend matrix lane (`artifacts/backend_recovery_matrix*`) and
bench receipt schema. Shape: backend name plus version become mandatory
receipt fields; a re-run of the standing bench on backend upgrade is a
defined event.

### F6. Hosted price-per-capability collapses 9x to 900x per year

Claim: the hosted-API price to reach a fixed capability threshold fell 9x to
900x per year depending on benchmark (median 50x across MMLU, GPQA Diamond,
MATH-500, MATH Level 5, HumanEval, and Arena ELO; 40x/year for GPT-4-level
GPQA Diamond), and the median rate is 200x/year for post-January-2024 data
(all figures high confidence against the source page). Caveat: the analysis
is dated 2025-03-12, so these rates describe the period through early 2025
and are themselves now roughly 16 months old.

Source: epoch.ai data insight, 2025-03-12. Exact URL path moderate
confidence: epoch.ai/data-insights, LLM inference price trends.

Why it matters: any $/token or cost-parity claim the platform publishes has a
half-life measured in months. The consequence is structural, not editorial:
cost receipts need a measurement date and a declared refresh cadence, and a
stale receipt should read as stale by construction.

Pour-back: the cost model inside the batch-1 $/token work (build candidate
B2) and `BATTLE-MAP.md` economics notes. Shape: every cost figure carries
measurement date plus an expiry window derived from these decay rates.

## 3. Honest nulls

N1. No published, measured, apples-to-apples $/token comparison of
single-user local inference vs hosted APIs at matched quality exists in the
sources found. Every located comparison either assumes high sustained
utilization for the local side or quotes datacenter batch-128 efficiency
that a batch-1 local box cannot reach. Flywheel would have to produce this
measurement itself.

N2. The popular claim that 4-bit weight quantization is basically free did
not survive long-context evaluation: https://arxiv.org/abs/2505.20276 shows
drops up to 59% on long-context tasks that short-context perplexity and
MMLU-style benchmarks miss, and the damage is model-family-specific
(Llama-3.1 70B and Qwen-2.5 72B diverge on the same quant).

N3. Speculative decoding gains are not universal: independent consumer-GPU
testing (inventivehq.com) found tens-of-percent to roughly 2x in practice,
content-dependent acceptance rates, and net slowdowns when the target model
is already small and fast. The 3.2x Apple Silicon result (F4) is a favorable
MoE-target case, not a floor.

N4. DGX Spark's headline compute advantage (roughly 2x achieved TFLOPS over
Strix Halo) did not translate to token generation: at 273 vs 256 GB/s the two
decode within roughly 7-13% of each other on the same 120B MoE model, so the
$1,050 price premium buys prefill speed only.

N5. Local models have not shown parity with hosted models on
repair/correction tasks: an April 2026 cloud-vs-local benchmark
(https://arxiv.org/abs/2604.18566) found local models scoring 0-50% on
error-fixing subtasks even when matching mid-tier cloud models (77%) on
extraction. Quality-per-dollar claims for local cannot yet be generalized
across task types.

N6. Sub-3-bit KV-cache quantization remains lossy without per-model,
per-layer tuning. Even KVTuner's nearly lossless floor moves between 3.25-bit
and 4.0-bit across two same-scale models, so no universal low-bit KV setting
has been demonstrated.

## 4. Dropped in verification

Eight findings from the sweep failed adversarial checking against their
sources and were dropped; they are not reproduced here.

## 5. Build candidates

### B1. Long-context quant gate for shipped artifacts

Grounded in F1 and N2. No quant artifact publishes without a long-context
eval delta recorded next to its short-context scores.

Pour-back target: bench harness plus the model release checklist in
`project-docs/release/`.

Smallest committable first slice: one fixed long-context QA/retrieval slice
(about 50 items) added to the existing harness, run on the current 14B
artifact at Q8_0 vs Q4_K_M, with the two-row delta committed as a receipt.

### B2. Batch-1 $/token receipt (the missing measurement)

Grounded in N1 and F6. Produce the comparison nobody has published: measured
single-user local cost vs hosted API cost at matched quality, dated, with a
declared expiry.

Pour-back target: `docs/research/` cost memo plus a script under `scripts/`.

Smallest committable first slice: a script that runs a fixed 20-prompt set on
the local box and emits a JSON receipt of tokens/s, wall time, model, quant,
backend, and hardware. Energy metering and the hosted-side comparison come in
later slices.

### B3. Per-model serving profile with mandatory receipts

Grounded in F2, F4, N3, and N6. KV bits and draft-model pairing become
per-model profile fields that are invalid without a pointer to the
measurement that justified them.

Pour-back target: serving configuration in `HARNESS.md` and the runtime
config schema.

Smallest committable first slice: the profile schema (kv_bits, draft_model,
receipt_path) plus one populated instance for one model, backed by a measured
before/after tokens-per-second A/B on this repo's task set.

### B4. Dated hardware and backend decision sheet

Grounded in F3, F5, and F6. A two-axis buying and configuration guide (memory
bandwidth for decode, achieved compute for prefill, backend version as a
measured variable) where every number carries source and date and the sheet
declares its own staleness rule.

Pour-back target: `docs/research/`, feeding the backend matrix lane under
`artifacts/backend_recovery_matrix*`.

Smallest committable first slice: a one-page sheet containing only the
confirmed numbers from F3 and F5 with sources and dates, plus the staleness
rule derived from F6.
