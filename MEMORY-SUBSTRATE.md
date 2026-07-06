# MEMORY SUBSTRATE — driving the marginal cost of verified inference toward ~0

> Operator directive (2026-07-03): "memory management integration natively, at a
> system level that reduces cost/bandwidth of compute to ~0." Taken literally,
> zero is impossible — every novel token, unique prefix, and novel oracle run
> has irreducible cost. The achievable and genuinely powerful target: the
> MARGINAL and AMORTIZED cost of everything SHARED or REPEATED goes to ~0. In a
> deep-search + flywheel system the shared/repeated fraction dominates, so cost
> per useful *verified* answer collapses toward the irreducible novel core. This
> is the systems layer beneath Layer B (the harness) — and the thing that makes
> deep verified search affordable on ONE 24 GB 4090.

## Why this is load-bearing, not gold-plating (the 24 GB math)

Qwen2.5-Coder-32B in 4-bit ≈ 18 GB weights on a 24 GB 4090, leaving ~5–6 GB for
KV + activations at inference. Qwen2.5-32B KV footprint (GQA: 64 layers × 8 KV
heads × 128 head_dim, fp16, k+v) ≈ 0.26 MB/token. A ~6 GB KV budget ≈ ~23K
tokens of KV TOTAL across all concurrent search branches. Best-of-N / tree
search wants hundreds–thousands of branches sharing long prompt + context
prefixes. Without KV reuse + tiering, deep search does not fit. The memory
substrate is what makes the slingshot's "spend lots of verified compute"
affordable at all.

## The six layers (HBM → CPU RAM → NVMe on E:, plus receipted caches)

1. **Prefix KV reuse (radix tree over token prefixes).** Every candidate in
   best-of-N / beam / tree search shares prompt + retrieved-context + partial
   -solution prefixes. Compute shared KV ONCE; the marginal cost of another
   candidate is only its *divergent suffix*. Over long shared prefixes, amortized
   prefix compute → ~0. (Backend: SGLang RadixAttention or vLLM automatic prefix
   caching; both serve 4-bit AWQ/GPTQ weights.)
2. **Paged KV + tiered eviction (HBM→CPU→NVMe).** PagedAttention pages KV in
   fixed blocks; cold prefixes evict HBM→CPU RAM→NVMe (E: 859 GB). A hot reload
   is bandwidth, not recompute — turning "recompute" into "reload," far cheaper
   for long contexts. KV becomes a first-class, tiered, persistent asset.
3. **Persistent cross-session / cross-iteration KV.** The system prompt and the
   retrieved-context envelopes (index/gather) are stable across tasks and across
   flywheel iterations over the same corpus; compute their KV once, persist to
   NVMe, reload on demand. Large saving across the flywheel's repeated passes.
4. **Content-addressed VERIFIED-RESULT cache (the receipt cache) — OUR IP.**
   key = hash(task_spec ⊕ retrieved_context ⊕ model_ref); value = {candidate,
   oracle_cmd, verdict:PASS, proof_envelope}. A HIT returns a *previously
   verified* answer with its receipt at ~0 compute — and it is SAFE because the
   receipt is re-checkable: re-run the (cheap) oracle to confirm non-staleness
   instead of re-running the (expensive) search. This is where "cost → 0" is
   literally true for repeated/similar verifiable tasks. It is the SAME store as
   the flywheel's verified-solution dataset: cache = training data = receipts,
   one artifact, three uses.
5. **Verifier memoization.** cache(candidate_hash → oracle_verdict). Identical
   candidates across branches/iterations are never re-verified. Oracle runs
   (pytest/cargo/Lean) are the expensive tail; memoizing drives repeated
   -verification cost → 0.
6. **Bandwidth reduction per token (decode is HBM-bandwidth-bound).**
   Speculative decoding with a small Qwen2.5-Coder draft (0.5B–1.5B) verifies K
   draft tokens per target pass → fewer target passes → less HBM traffic per
   accepted token (typically 2–3× tok/s). Quantized KV (fp8/int4) halves/quarters
   KV footprint + bandwidth → longer contexts + more concurrent branches in 24 GB.

## Native vs backend (respecting the zero-dep-first principle)

- **Native / ours (the differentiator):** the content-addressed verified-result
  cache, verifier memoization, the tiering policy + persistence to E:, and the
  invalidation/staleness protocol (keyed on model_ref + oracle_cmd + context
  hash so a changed model, oracle, or context misses correctly). This is our IP,
  and it is where receipts make aggressive caching *safe*.
- **Optional mature backend (where zero-dep cannot win):** the attention-kernel
  -level paged/radix KV (SGLang / vLLM / exllamav2). Reimplementing production KV
  kernels is not where we win; we orchestrate a mature engine and own the
  receipted memory layer above it.

## Correctness invariant (caching must never break "no receipt, no accept")

A cache hit is accepted only if its proof envelope re-checks under the CURRENT
oracle. Keys bind model_ref, oracle_cmd, and context hash; any drift → miss.
Verified-result hits are revalidated by re-running the cheap oracle
(compile/test) before serving — search is skipped, verification is not.
Staleness therefore cannot produce a wrong accepted answer; worst case is a
re-search. The memory substrate stays inside the reconcile discipline.

## Integration + build order (folds into HARNESS Phase 4)

- **P4.0** Verified-result cache + verifier memoization (native, content
  -addressed on E:). Milestone: a repeated task returns a re-checked receipt at
  ~0 search cost.
- **P4.1** Prefix-caching serving backend for the 4-bit 32B; measure tok/s and
  KV headroom. Milestone: best-of-N over a shared prefix shows near-flat cost vs
  N (marginal → ~0).
- **P4.2** Tiered KV persistence (HBM→CPU→NVMe) + persistent context-envelope
  KV. Milestone: long-context search fits and reload beats recompute wall-clock.
- **P4.3** Speculative decoding (small draft) + quantized KV. Milestone:
  measured tok/s uplift; more concurrent branches at fixed VRAM.

## Honest limits

Irreducible cost remains for: the divergent suffix of each *novel* candidate,
the first computation of each *unique* prefix, and *novel* oracle runs. Cache
hit-rate governs how close to ~0 the system runs; on wholly novel tasks the
substrate delivers KV-reuse + bandwidth wins only (still large), not the cache
win. NVMe reload has real latency; tiering helps long-context / cross-branch
reuse, not a single short novel generation.
