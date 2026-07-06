export const meta = {
  name: 'memory-substrate',
  description: 'Design the native system-level memory substrate that drives marginal verified-inference cost/bandwidth toward ~0 on one 24GB 4090',
  phases: [
    { title: 'Survey', detail: 'KV-reuse serving systems + caching/quantization/speculative, with real numbers' },
    { title: 'Design', detail: '3 substrate designs: reuse-hierarchy, verified-result-cache, bandwidth' },
    { title: 'Adversary', detail: 'refute the ~0 claim, cache-correctness, 24GB feasibility' },
    { title: 'Synthesize', detail: 'winning memory substrate spec + honest zero claim + build order' },
  ],
}

const CONTEXT = `
GOAL: design a NATIVE, system-level MEMORY SUBSTRATE beneath a verified-inference
harness. The harness makes a local Qwen2.5-Coder-32B (QLoRA-adapted, 4-bit,
served on ONE 24GB RTX 4090) BEAT frontier single-shot on VERIFIABLE tasks by
spending lots of oracle-verified test-time search, with every accepted answer
carrying a re-checkable proof. The substrate must drive the MARGINAL and
AMORTIZED cost/bandwidth of everything SHARED or REPEATED toward ~0, so deep
search is affordable on one GPU. Literal zero is impossible (irreducible: the
divergent suffix of each novel candidate, first compute of each unique prefix,
novel oracle runs) -- be precise about what actually approaches ~0 and what does
not.

HARDWARE: one 24GB RTX 4090 (~1 TB/s HBM). 32B 4-bit ~18GB weights -> ~6GB for
KV+activations. Qwen2.5-32B KV ~0.26 MB/token (GQA 64 layers x 8 KV heads x 128
head_dim, fp16) -> ~6GB ~= ~23K tokens of KV total across ALL branches. NVMe on
E: has 859GB free; CPU RAM available as a mid tier.

ASSETS (organs): crucible (verifier/witness), index (code retrieval), gather
(external retrieval with receipts), forum (orchestration), telos. Real oracles:
pytest/mypy, cargo, Lean/Coq, sympy/mpmath.

CURRENT SPEC: read C:/dev/local-model/MEMORY-SUBSTRATE.md and HARNESS.md. Build
on the six layers (prefix KV reuse, paged tiered KV HBM->CPU->NVMe, persistent
cross-iteration KV, content-addressed verified-result cache, verifier
memoization, speculative decoding + quantized KV). Improve, quantify, or refute.

INVARIANT: caching must never break "no receipt, no accept" -- a cache hit is
accepted only if its proof re-checks under the CURRENT oracle. Attack this.
PRINCIPLE: native/ours where it is the differentiator (receipted verified-result
cache, memoization, tiering policy, invalidation protocol); optional mature
backend (SGLang/vLLM/exllamav2) only for attention-kernel-level paged/radix KV.
`

const LENSES = [
  { key: 'serving', name: 'KV-cache reuse & serving systems',
    brief: 'RadixAttention (SGLang), vLLM automatic prefix caching + PagedAttention, LMCache, Mooncake KV store, exllamav2 paged cache, KV offload to CPU/NVMe. Get REAL throughput/VRAM numbers for a 4-bit ~32B on a 24GB GPU, and how prefix reuse scales best-of-N cost with N.' },
  { key: 'cache', name: 'Caching, memoization, KV quantization, speculative decoding',
    brief: 'prompt/prefix caching to disk, content-addressed + semantic result caching, KV quantization (fp8/int4) accuracy vs savings, speculative/assisted decoding (draft models, EAGLE, Medusa) tok/s gains and HBM-bandwidth effects. Real numbers where they exist.' },
]

const PHILS = [
  { key: 'reuse', name: 'KV-reuse-and-hierarchy-first',
    bet: 'Radix prefix reuse + paged tiered KV (HBM->CPU->NVMe) + persistent context-envelope KV drive marginal PREFIX/CONTEXT compute to ~0 so thousands of shared-prefix branches fit and cost near-flat vs N.' },
  { key: 'vcache', name: 'Verified-result-cache-first',
    bet: 'A content-addressed receipted verified-result cache + verifier memoization is the primary ~0-cost mechanism: repeated/similar verifiable tasks return a re-checked proof instead of re-searching. The store doubles as the flywheel training set. Own correctness/invalidation.' },
  { key: 'bandwidth', name: 'Bandwidth-first',
    bet: 'Decode is HBM-bandwidth-bound; speculative decoding with a small draft + quantized KV minimize HBM traffic per verified token, maximizing verified search throughput on one 4090.' },
]

const ADV = [
  { key: 'zerocost', name: 'Zero-cost-reality',
    brief: 'Quantify whether marginal/amortized cost actually approaches ~0. Where does it NOT (low cache hit-rate, wholly novel tasks, NVMe reload latency, radix-tree/bookkeeping overhead, eviction thrash)? Give numbers and name the regimes where the claim fails.' },
  { key: 'correctness', name: 'Cache-correctness',
    brief: 'Can a stale or mis-keyed cache hit produce a WRONG accepted answer, violating no-receipt-no-accept? Attack the invalidation/staleness/keying protocol: model updates, oracle changes, context drift, hash collisions, nondeterministic oracles.' },
  { key: 'hardware', name: '24GB/32B-feasibility',
    brief: 'Real VRAM/KV/tok-s math for a 4-bit 32B + prefix cache + tiering + speculative draft on ONE 4090. Does the draft model + target + KV all fit? Where does it OOM or thrash between tiers? Is the PCIe/NVMe bandwidth enough for reload to beat recompute?' },
]

const DESIGN_SCHEMA = { type: 'object', properties: {
  philosophy: { type: 'string' }, substrate_name: { type: 'string' },
  layers: { type: 'array', items: { type: 'object', properties: {
    name: { type: 'string' }, mechanism: { type: 'string' },
    reduces: { type: 'string' }, backend: { type: 'string' },
  }, required: ['name', 'mechanism'] } },
  what_reaches_zero: { type: 'string' },
  what_stays_irreducible: { type: 'string' },
  hardware_fit_24gb: { type: 'string' },
  quantified_savings: { type: 'string' },
  correctness_story: { type: 'string' },
  risks: { type: 'array', items: { type: 'string' } },
  build_order: { type: 'array', items: { type: 'string' } },
}, required: ['philosophy', 'substrate_name', 'layers', 'what_reaches_zero', 'hardware_fit_24gb'] }

const VERDICT_SCHEMA = { type: 'object', properties: {
  design_ref: { type: 'string' }, lens: { type: 'string' },
  verdict: { type: 'string', enum: ['strong', 'viable', 'weak', 'broken'] },
  fatal_flaws: { type: 'array', items: { type: 'string' } },
  survivable_flaws: { type: 'array', items: { type: 'string' } },
  required_fixes: { type: 'array', items: { type: 'string' } },
  strongest_point: { type: 'string' }, quantified_check: { type: 'string' },
}, required: ['design_ref', 'lens', 'verdict'] }

const SYNTH_SCHEMA = { type: 'object', properties: {
  substrate_name: { type: 'string' },
  honest_zero_claim: { type: 'string' },
  layers: { type: 'array', items: { type: 'object', properties: {
    name: { type: 'string' }, mechanism: { type: 'string' },
    reduces: { type: 'string' }, native_or_backend: { type: 'string' },
  }, required: ['name', 'mechanism'] } },
  correctness_invariant: { type: 'string' },
  hardware_plan_24gb: { type: 'string' },
  quantified_savings: { type: 'string' },
  build_order: { type: 'array', items: { type: 'object', properties: {
    phase: { type: 'string' }, deliverable: { type: 'string' },
    verifiable_milestone: { type: 'string' },
  }, required: ['phase', 'deliverable'] } },
  risks_and_mitigations: { type: 'array', items: { type: 'object', properties: {
    risk: { type: 'string' }, mitigation: { type: 'string' },
  }, required: ['risk', 'mitigation'] } },
  honest_limits: { type: 'string' },
}, required: ['substrate_name', 'honest_zero_claim', 'layers', 'correctness_invariant', 'hardware_plan_24gb', 'build_order'] }

const surveyPrompt = (l) => `${CONTEXT}

YOUR LENS: ${l.name}. ${l.brief}

Enumerate the strongest concrete techniques/systems in this lens, each with:
mechanism, real numbers (throughput, VRAM, savings, accuracy impact) where they
exist, whether it fits a 4-bit 32B on a 24GB 4090, and maturity/risk. Use web
search to ground claims in real systems and results (2023-2026). Return a JSON
object with fields {lens, techniques:[{name,mechanism,numbers,fits_24gb,maturity,risk,refs:[]}], takeaway}.`

const designPrompt = (p, menu) => `${CONTEXT}

DESIGN PHILOSOPHY: ${p.name}. Core bet: ${p.bet}

Surveyed systems/numbers (JSON):
${menu}

Design the memory substrate under this philosophy. Specify layers (each:
mechanism, what cost/bandwidth it reduces, native-vs-backend), exactly WHAT
reaches ~0 and WHAT stays irreducible, the 24GB hardware fit with real KV/VRAM
/tok-s math, quantified savings, the correctness story (how caching stays inside
no-receipt-no-accept), risks, and a build order. Return the structured schema.`

const advPrompt = (d, al) => `${CONTEXT}

You are an ADVERSARIAL reviewer. LENS: ${al.name}. ${al.brief}

DESIGN UNDER REVIEW (JSON):
${JSON.stringify(d)}

Try hard to REFUTE it under your lens. Give fatal flaws, survivable flaws,
required fixes, the single strongest point, and a quantified check. Be
skeptical of any "~0" claim: state precisely the regime where it holds and where
it breaks. Return the structured verdict.`

const synthPrompt = (judged) => `${CONTEXT}

All candidate substrate designs with adversarial verdicts (JSON):
${judged}

Synthesize the WINNING memory substrate that SURVIVES review. Deliver every
schema field, especially:
- honest_zero_claim: a precise statement of what marginal/amortized cost reaches
  ~0, in which regimes, and what stays irreducible. No overclaim.
- layers: the surviving mechanisms, each marked native-or-backend.
- correctness_invariant: how the caches provably cannot produce a wrong accepted
  answer (keying, revalidation, drift -> miss).
- hardware_plan_24gb: concrete KV/VRAM/tok-s plan for a 4-bit 32B + prefix cache
  + tiering + speculative draft on ONE 4090.
- quantified_savings: expected marginal-cost reduction with real numbers.
- build_order: concrete, each with a verifiable milestone.
- honest_limits: where the ~0 claim does not apply.
This becomes MEMORY-SUBSTRATE v2. Return the structured schema.`

phase('Survey')
const survey = (await parallel(LENSES.map((l) => () =>
  agent(surveyPrompt(l), { agentType: 'scholar', phase: 'Survey', label: `survey:${l.key}`, effort: 'high' })
))).filter(Boolean)
log(`survey: ${survey.length}/${LENSES.length} lenses`)

phase('Design')
const menu = JSON.stringify(survey)
const designs = (await parallel(PHILS.map((p) => () =>
  agent(designPrompt(p, menu), { schema: DESIGN_SCHEMA, phase: 'Design', label: `design:${p.key}`, effort: 'high' })
))).filter(Boolean)
log(`designs: ${designs.length}/${PHILS.length}`)

phase('Adversary')
const judged = (await parallel(designs.map((d) => () =>
  parallel(ADV.map((al) => () =>
    agent(advPrompt(d, al), { schema: VERDICT_SCHEMA, phase: 'Adversary', label: `adv:${d.philosophy || 'design'}:${al.key}`, effort: 'high' })
  )).then((vs) => ({ design: d, verdicts: vs.filter(Boolean) }))
))).filter(Boolean)
log(`adversary: judged ${judged.length}`)

phase('Synthesize')
const synth = await agent(synthPrompt(JSON.stringify(judged)), { schema: SYNTH_SCHEMA, phase: 'Synthesize', label: 'synthesize', effort: 'max' })
return synth
