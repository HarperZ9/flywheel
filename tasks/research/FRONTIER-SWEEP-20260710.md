# Frontier sweep 2026-07-10 -- ten fused concepts vs the verified-inference thesis

Output of a 21-agent multi-domain research workflow (live web sources, each
concept researched -> threaded into our system -> adversarially synthesized).
The operator supplied a batch of terms + links + a fused "method" sentence.

## Meta-finding: real tokens, fabricated compounds, one clause a theorem forbids

Every individual token points at genuine, active 2023-2026 research. The FUSED
objects ("golden strassen clifford toroidal field", "torsional twistor markov
pump") return zero literature hits -- word-salad bolting unrelated fields that
are combined nowhere. "pump" names nothing.

| Token | Real anchor | Status |
|---|---|---|
| clifford | Clifford-group-equivariant nets, GATr (Ruhe/Brehmer NeurIPS 2023; TMLR 2025) | established |
| strassen | AlphaTensor (Nature 2022), AlphaEvolve rank-48 (2025), Dumas-Pernet-Sedoglavic (2506.13242) | established |
| toroidal | grid-cell 2-torus (Gardner, Nature 2022); toroidal/hyperspherical latents (2026) | established/emerging |
| twistor | twistor / amplituhedron / positive geometry (Galashin 2410.09574) | established physics |
| markov | flow-based MCMC / gauge-equivariant flows; MCTS in AlphaTensor | established |
| golden | Penrose / aperiodic-monotile tilings; "Penrose tiling is a QEC code" (Li-Boyle 2311.13040) | established math |
| "infinite tessellation, no data loss, + compression" | INR / seed compression (COIN, NeRV, NVRC, SeedLM) | established but **LOSSY** |

**The line is a theorem, not my training cutoff.** Most of this postdates a
Jan-2026 memory and was verified live; "I don't know it" is never the
disqualifier. The synthesis clause "infinite tessellation *without data loss*
while *maintaining compression*" is forbidden by Shannon/Kolmogorov: lossless
compression of arbitrary data below its entropy is provably impossible (counting
argument). Neural fields ARE resolution-independent, but the extra detail is
invented/interpolated, not recovered -- plausible pixels, not information.
"Lossless infinite compression" conflates resolution-independence (real) with
beating entropy (impossible). That fusion is dead on a proof; no live research
moves it.

## Ranked

| Concept | Reality | Threads in | Rank |
|---|---|---|---|
| Fast matmul discovery (AlphaTensor/AlphaEvolve/Dumas) | established | yes | **ACTIONABLE** |
| J-lens / J-space workspace + NLAs (Anthropic 2026) | emerging | yes | **ACTIONABLE** |
| VSA / HDC holographic associative memory | established | yes | INSPIRATION |
| Clifford / GA equivariant nets (GATr) | established | partial | INSPIRATION |
| INR / procedural-seed compression (SeedLM, NVRC) | established | yes | INSPIRATION |
| Flow-based MCMC / gauge-equivariant flows | established | yes | INSPIRATION |
| Toroidal / topological representations | established/emerging | partial | INSPIRATION |
| Compounding-context / agent memory (context.store, MCP) | established | yes | INSPIRATION |
| Aperiodic monotiles (hat/spectre, Penrose) | emerging | **no** | **NOISE** |

## ACTIONABLE -- done this pass

1. **Fast matmul discovery** -> `harness/matmul_oracle.py` + calibration + tests
   (8/8). The thesis in the wild: search proposes a rank-R bilinear decomposition,
   an exact symbolic tensor identity disposes, the proposer is off the accept path.
   Ships as a runnable oracle (accepts a scheme only if it reproduces the exact
   n*m*p tensor over the rationals; calibrates zero-false-accept over a
   Strassen-7 / naive / perturbed / rank-dropped ladder). The harness's first
   hard-symbolic, ring-parameterized oracle. Provenance note added to PROJECT.md 5.
   *Honest bound:* exactness earns over a random-matrix probe on ring-generality +
   zero false-accept probability, not raw discrimination (Freivalds is near-exact).
2. **J-lens / J-space** -> demote-only `harness/workspace_lens.py` (built + tested
   last pass); sourcing corrected (Festyve = deepseek-coder-1.3b lens; solarkyle =
   broader registry with code-model lenses gpt-oss-20b / Qwen3.6-27B + router
   weights, works across quant). Next empirical step (needs GPU + a fit): run a
   code-model lens over the 61 headroom tasks; pre-falsifier = heatmap must differ
   on solved vs never-solved tasks; deploy-falsifier = demoted subset must have a
   strictly lower oracle-pass rate.

## Honest negatives (kept explicit)

- **Aperiodic monotiles = NOISE.** Li-Boyle (a Penrose tiling IS a QEC code) is
  real, but it INVERTS our need: QEC gives tamper-TOLERANCE (bounded local change
  recovered); `transitive_witness.py` is fail-closed for tamper-EVIDENCE (any
  ancestor drift -> UNVERIFIABLE). Surface resemblance, opposite mechanism; the
  real primitive needs a quantum substrate this box lacks.
- **Rejected sub-threads inside real items:** GATr as a proposer (off-thesis --
  our lane is code, moat is Layer B not weights per the HumanEval CPT negative);
  SeedLM to "fit the 32B" (32B blocker is activation memory on the fp32 upcast,
  not weight storage); twistor geometry (NOISE for a code harness); AlphaEvolve's
  self-improvement update (predates cutoff, already mirrored by evolve/flywheel/mcts).
- **Equivariance + topology threads are INSPIRATION not ACTIONABLE:** the
  buildable-today slice of GA is generic metamorphic testing (idempotence,
  involution, permutation-invariance); the GA-specific + toroidal-carrier content
  need a geometry/periodic-signal task lane we do not have (the grid-transpile
  probe returned COPY-ONLY and is parked). Revisit only if a domain change makes
  their falsifiers capable of firing -- today the multiplicity diagnosis (77% of
  headroom tasks have 0 correct candidates at N=4) predicts they rescue ~nothing.

## Parked INSPIRATION with the trigger that would un-park it

- VSA/HDC-similarity consensus clustering in `selector.py` -- un-park if exact-repr
  clustering proves too brittle on a measured task set.
- Receipt-gated `proof_cache` + verified `wiki` exposed as an MCP memory server --
  un-park when real agent traffic wants a shared, drift-checked context store.
