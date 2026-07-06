export const meta = {
  name: 'slingshot-architecture',
  description: 'Design the verified-inference architecture that makes a local 32B beat frontier single-shot on verifiable tasks',
  phases: [
    { title: 'Survey', detail: 'research 6 families of test-time-compute + verification techniques' },
    { title: 'Design', detail: '4 complete architectures from distinct philosophies' },
    { title: 'Adversary', detail: 'refute each design vs frontier + 24GB/32B feasibility' },
    { title: 'Synthesize', detail: 'winning architecture + wings + build order + novelty' },
  ],
}

const CONTEXT = `
GOAL: make a LOCAL Qwen2.5-Coder-32B (QLoRA-adapted, served on ONE 24GB RTX 4090)
produce answers that BEAT a frontier model single-shot answer on VERIFIABLE
tasks (code that compiles + passes tests, proofs that type-check, math that checks
out, anything with an oracle) -- and, unlike frontier single-shot, ship every
accepted answer with a re-checkable PROOF. Matching frontier is NOT enough; we
want to EXCEED it on the verifiable slice and mark the irreducibly-unverifiable
remainder honestly as UNVERIFIABLE.

ASSETS (organs already built, usable as backends):
- crucible: verifier / judgment organ (register -> steelman -> measure -> witness
  MATCH / DRIFT / UNVERIFIABLE).
- index: code/symbol retrieval + context envelopes over a large local ecosystem.
- gather: external knowledge retrieval with source receipts.
- forum: multi-agent orchestration with a witnessed causal ledger.
- telos: model_foundry / learning_forge / measurement_layers / proof.
Plus real oracles: pytest / mypy, cargo build + test, Lean / Coq, sympy / mpmath.

CONSTRAINTS: single 24GB RTX 4090. 32B in 4-bit approx 18GB. We CAN train the
model (QLoRA), not just prompt it. Local inference only for the proposer; frontier
models may be called only as BASELINES to beat.

CURRENT DESIGN: read C:/dev/local-model/HARNESS.md and C:/dev/local-model/ROADMAP.md
for the existing plan (escalating verifier-guided search + proof envelopes + a
verified-output self-improvement flywheel). Build on it, improve it, or refute it.
`

const LENSES = [
  { key: 'sampling', name: 'Repeated sampling & selection',
    brief: 'pass@k scaling, best-of-N, self-consistency / majority vote, sample budgets, temperature & nucleus effects, weighted voting, sample-then-rank. How far does sheer verified sampling scale toward beating frontier?' },
  { key: 'search', name: 'Structured search & planning',
    brief: 'beam search, tree-of-thought, MCTS, LATS, A*, verifier-guided / reward-guided decoding, step-level search over an oracle reward.' },
  { key: 'verify', name: 'Verification & reward models',
    brief: 'outcome vs process reward models (PRM), generative / LLM verifiers, self-verification, debate, verifier training from oracle labels, calibration, false-accept control.' },
  { key: 'speed', name: 'Inference throughput to AFFORD deep search',
    brief: 'speculative / assisted decoding (draft models, Medusa, EAGLE), quantized serving (exllamav2, AWQ, GPTQ, Marlin, vLLM), paged KV-cache, continuous batching. More tok/s = more verified search per second on one 4090.' },
  { key: 'retrieve', name: 'Retrieval & knowledge carrying',
    brief: 'RAG, agentic / iterative retrieval, long-context vs retrieval tradeoffs, repo-level code retrieval, tool-augmented reasoning, grounding with source receipts (our index + gather).' },
  { key: 'selfimprove', name: 'Self-improvement flywheels (candidate WINGS)',
    brief: 'STaR, rejection-sampling fine-tuning (RFT/ReST), RL from verifier reward (RLVR / GRPO / PPO), Reflexion, self-refine, expert iteration, AlphaZero-style search+learn loops applied to code/proofs. Scrutinize whether it can push the local model PAST frontier over iterations, and its collapse / reward-hacking / forgetting risks.' },
]

const PHILS = [
  { key: 'throughput', name: 'Throughput-first',
    bet: 'Maximize verified search per wall-clock second. Fast quantized serving + speculative decoding fund a large escalating best-of-N / beam under real oracles. Bet: sheer verified sample volume beats frontier single-shot on verifiable tasks TODAY, no training loop required.' },
  { key: 'verifier', name: 'Verifier-first',
    bet: 'Make the VERIFIER the intelligence. Escalating oracle registry + a process reward model + verifier-guided tree search (MCTS-lite). Bet: precise step-level verification steers a weaker proposer to frontier-beating solutions.' },
  { key: 'flywheel', name: 'Self-improvement-first (AlphaZero-for-code)',
    bet: 'Make the SYSTEM learn. The harness oracle-verified solutions become RFT / RLVR training data; expert iteration lifts the proposer single-shot toward and past frontier ON the verifiable distribution. Bet: search + verify + learn compounds.' },
  { key: 'integrated', name: 'Integrated / composition',
    bet: 'Combine the best of the above into one coherent system with the cleanest interfaces to crucible / index / gather / forum, whose proof-carrying outputs are both frontier-beating AND uniquely trustworthy.' },
]

const ADV = [
  { key: 'beats', name: 'Does-it-actually-beat-frontier',
    brief: 'Refute the claim that this beats frontier single-shot on verifiable tasks. Where does it merely MATCH or LOSE? Consider tasks where the 32B proposer has ~0 pass@k (search cannot find what the model never proposes), verifier false-accepts, oracle-coverage gaps, and fairness of wall-clock / token budget vs the frontier baseline.' },
  { key: 'hardware', name: '24GB/32B-feasibility',
    brief: 'Refute hardware feasibility on ONE 4090. 32B 4-bit ~18GB + serving KV-cache + search parallelism + concurrent verifier processes + (if training) QLoRA memory. Does the claimed search / throughput budget actually exist? Quantify tok/s and VRAM. Where does it OOM or get too slow to matter?' },
  { key: 'flywheel', name: 'Flywheel-convergence',
    brief: 'If there is a learning loop, refute that it compounds. Reward hacking against the oracle, distribution collapse, verifier overfitting, catastrophic forgetting of general ability, the oracle-coverage ceiling. Does it actually push past frontier or plateau / collapse?' },
]

const SURVEY_SCHEMA = { type: 'object', properties: {
  lens: { type: 'string' },
  techniques: { type: 'array', items: { type: 'object', properties: {
    name: { type: 'string' }, mechanism: { type: 'string' },
    expected_lift: { type: 'string' }, compute_cost: { type: 'string' },
    fits_4090_32b: { type: 'boolean' }, composes_with_organs: { type: 'string' },
    maturity: { type: 'string' }, risk: { type: 'string' },
    refs: { type: 'array', items: { type: 'string' } },
  }, required: ['name', 'mechanism', 'expected_lift', 'fits_4090_32b'] } },
  lens_takeaway: { type: 'string' },
  top_picks: { type: 'array', items: { type: 'string' } },
}, required: ['lens', 'techniques', 'lens_takeaway'] }

const DESIGN_SCHEMA = { type: 'object', properties: {
  philosophy: { type: 'string' }, architecture_name: { type: 'string' },
  components: { type: 'array', items: { type: 'object', properties: {
    name: { type: 'string' }, role: { type: 'string' },
    technique: { type: 'string' }, backing_organ: { type: 'string' },
  }, required: ['name', 'role'] } },
  data_flow: { type: 'string' },
  how_it_beats_frontier: { type: 'array', items: { type: 'string' } },
  compute_budget_story: { type: 'string' },
  hardware_fit_24gb: { type: 'string' },
  novelty_claim: { type: 'string' },
  risks: { type: 'array', items: { type: 'string' } },
  build_order: { type: 'array', items: { type: 'string' } },
}, required: ['philosophy', 'architecture_name', 'components', 'how_it_beats_frontier', 'hardware_fit_24gb'] }

const VERDICT_SCHEMA = { type: 'object', properties: {
  design_ref: { type: 'string' }, lens: { type: 'string' },
  verdict: { type: 'string', enum: ['strong', 'viable', 'weak', 'broken'] },
  fatal_flaws: { type: 'array', items: { type: 'string' } },
  survivable_flaws: { type: 'array', items: { type: 'string' } },
  required_fixes: { type: 'array', items: { type: 'string' } },
  strongest_point: { type: 'string' }, quantified_check: { type: 'string' },
}, required: ['design_ref', 'lens', 'verdict'] }

const SYNTH_SCHEMA = { type: 'object', properties: {
  architecture_name: { type: 'string' }, one_line_thesis: { type: 'string' },
  how_it_beats_frontier: { type: 'array', items: { type: 'string' } },
  the_wings: { type: 'string' },
  components: { type: 'array', items: { type: 'object', properties: {
    name: { type: 'string' }, role: { type: 'string' },
    technique: { type: 'string' }, backing_organ: { type: 'string' },
  }, required: ['name', 'role'] } },
  data_flow: { type: 'string' },
  hardware_plan_24gb_32b: { type: 'string' },
  novelty_for_publication: { type: 'array', items: { type: 'string' } },
  eval_protocol: { type: 'string' },
  build_order: { type: 'array', items: { type: 'object', properties: {
    phase: { type: 'string' }, deliverable: { type: 'string' },
    depends_on: { type: 'string' }, verifiable_milestone: { type: 'string' },
  }, required: ['phase', 'deliverable'] } },
  risks_and_mitigations: { type: 'array', items: { type: 'object', properties: {
    risk: { type: 'string' }, mitigation: { type: 'string' },
  }, required: ['risk', 'mitigation'] } },
  honest_limits: { type: 'string' },
}, required: ['architecture_name', 'one_line_thesis', 'how_it_beats_frontier', 'the_wings', 'components', 'build_order', 'novelty_for_publication'] }

const surveyPrompt = (l) => `${CONTEXT}

YOUR LENS: ${l.name}. ${l.brief}

Enumerate the strongest concrete techniques in this lens for BEATING frontier
single-shot on verifiable tasks. For each: mechanism, expected accuracy lift
(cite real numbers where they exist), compute cost, whether it fits 24GB/32B,
how it composes with our organs, maturity, risk, key references (2023-2026).
Use web search to ground claims in real methods/results. Prioritize what pushes
PAST frontier, not merely matches. Return the structured schema.`

const designPrompt = (p, menu) => `${CONTEXT}

DESIGN PHILOSOPHY: ${p.name}. Core bet: ${p.bet}

Full menu of surveyed techniques (JSON):
${menu}

Design a COMPLETE architecture under this philosophy that makes our local 32B
beat frontier single-shot on verifiable tasks. Specify components (each mapped
to a technique and, where relevant, a backing organ), the data flow, exactly
HOW it beats frontier (mechanism not wish), the compute-budget story on ONE
4090, the 24GB hardware fit, the novelty claim, risks, and a build order.
Be concrete and quantitative. Return the structured schema.`

const advPrompt = (d, al) => `${CONTEXT}

You are an ADVERSARIAL reviewer. LENS: ${al.name}. ${al.brief}

DESIGN UNDER REVIEW (JSON):
${JSON.stringify(d)}

Try hard to REFUTE it under your lens. Give fatal flaws (kill the claim),
survivable flaws (fixable), required fixes, and the single strongest point.
Quantify where possible (VRAM math, tok/s, pass@k, wall-clock). Default to
skepticism: if under your lens it only MATCHES frontier rather than beating it,
say so and mark verdict accordingly. Return the structured verdict.`

const synthPrompt = (judged) => `${CONTEXT}

All candidate designs with their adversarial verdicts (JSON):
${judged}

Synthesize the WINNING integrated architecture that SURVIVES adversarial review.
Take the strongest surviving mechanisms across designs, discard refuted ones,
apply required fixes. Deliver every field of the schema, especially:
- how_it_beats_frontier: the concrete mechanisms (not wishes).
- the_wings: the specific compounding / unbounded-verified-compute / self-
  improvement mechanism giving DURABLE edge past frontier, AND why it converges
  rather than collapses (address reward-hacking / forgetting / oracle ceiling).
- hardware_plan_24gb_32b: concrete VRAM + throughput plan on ONE 4090.
- build_order: concrete, each with a verifiable milestone, mapped to our organs.
- honest_limits: where it stays UNVERIFIABLE or frontier still wins.
This becomes HARNESS v2. Return the structured schema.`

phase('Survey')
const survey = (await parallel(LENSES.map((l) => () =>
  agent(surveyPrompt(l), { agentType: 'scholar', schema: SURVEY_SCHEMA, phase: 'Survey', label: `survey:${l.key}`, effort: 'high' })
))).filter(Boolean)
log(`survey: ${survey.length}/${LENSES.length} lenses returned`)

phase('Design')
const menu = JSON.stringify(survey)
const designs = (await parallel(PHILS.map((p) => () =>
  agent(designPrompt(p, menu), { schema: DESIGN_SCHEMA, phase: 'Design', label: `design:${p.key}`, effort: 'high' })
))).filter(Boolean)
log(`designs: ${designs.length}/${PHILS.length} produced`)

phase('Adversary')
const judged = (await parallel(designs.map((d) => () =>
  parallel(ADV.map((al) => () =>
    agent(advPrompt(d, al), { schema: VERDICT_SCHEMA, phase: 'Adversary', label: `adv:${d.philosophy || 'design'}:${al.key}`, effort: 'high' })
  )).then((vs) => ({ design: d, verdicts: vs.filter(Boolean) }))
))).filter(Boolean)
log(`adversary: judged ${judged.length} designs`)

phase('Synthesize')
const synth = await agent(synthPrompt(JSON.stringify(judged)), { schema: SYNTH_SCHEMA, phase: 'Synthesize', label: 'synthesize', effort: 'max' })
return synth
