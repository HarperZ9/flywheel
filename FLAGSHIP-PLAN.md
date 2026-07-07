# Flagship Establishment Plan

Where each of the seven flagship categories actually stands, what genuinely
separates it from the industry best, and the single next increment that earns
the gap closed. Grounded by a 7-agent assessment sweep over real files
(2026-07-07, run `wf_643cfd70-9cb`, full JSON in the session record) plus a
ranking synthesis. Maturity labels are honest and appear verbatim in any
public copy. No category is called a flagship here; the honest labels are one
tested-component, two demos, four kernels.

## The mission this plan serves

**Best tool in every single category entered, and integrative niches that had
never existed.** Two prongs. First: feature-for-feature superiority against
the current best in each category — features, UX, demos, speed, cost. A new
competitor is assessed as a whole product before anything else; the
accountability layer is the closing multiplier, never the lede, because it
does not bring users in on its own. Second: where a category is crowded,
create the adjacent category with no incumbent by composing organs nobody
else has — the context lens (live budget-frontier replay), the workbench
spine view (tool mutual-awareness rendered), proof-addressed memory
(verified-result reuse, not billing-cache reuse).

## The rule this plan lives under

Every capability sentence must name the falsifier that fired. If none fired,
the sentence does not ship. The retired example: the M7 "+10% lift" collapsed
under ablation (single 80% / verified-external 80% / verified-self 80%, N=10,
one task, no CI). That number is quarantined. No lift figure appears in any
public-facing file unless it cites an N>=100 matched-budget run with
escalation ON vs flat best-of-N and a frontier baseline.

## Ranking (foundation strength x leverage x buildable now)

### 1. Harness (verified-inference) — demo
The strongest real foundation: 62 modules, ~300 green tests, M1-M4 loop
reproducible at 100% receipt reproducibility. The 2026-07-06 arXiv sweep of 19
papers found the transitive-witness closure unclaimed; the substrate (a
provenance DAG) is prior art, the re-witnessing closure on it is not.

**Increment #1: SHIPPED 2026-07-07.** The closure is wired into
`run_loop`'s accept path (`harness/grounding.py`, opt-in
`grounding_recheck=True`). The three-arm falsifier fired end-to-end on real
envelopes (`tests/test_grounding_closure.py`): tampered ancestor A
re-witnesses DRIFT; task B citing A returns UNVERIFIABLE (gap, not glut) and
is refused even though its own oracle passes; independent task C stays MATCH.
Fail-closed both directions: an unlocatable grounding or a missing oracle
environment is UNVERIFIABLE, never assumed MATCH and never faked with a
wrong-workdir re-run. The pre-wire path accepts the same poisoned setup; the
wired path refuses. That sentence is the whole claim.

Remaining gap to Claude Code / OpenHands / SWE-agent / Devin: they win on
capability and integration breadth; this harness's differentiator is the
accountability layer they do not have (measured by
`harness/accountability_bench.py`, where an unaccountable strawman scores 0.0
by construction). Next: score THEM on the bench, not ourselves.

### 2. Dataset trainer — kernel
Deterministic corpus -> manifest -> shards -> QLoRA CPT, safety-gated
allowlist (non-overrideable deny list). Missing: the provenance chain does not
reach the checkpoint; shards are opaque.
**Increment:** a versioned corpus card + dataset receipt written beside the
trained adapter (allowlist hash, manifest content hash, tokenizer hash, shard
hashes, trainer config). Falsifier: mutate one corpus file, re-derive, the
receipt must flag CORPUS_DRIFT; byte-identical corpus must reproduce the
receipt. ~100 lines, zero new dependencies.

### 3. Local models — tested-component
14B CPT complete (checkpoint-2020, train_loss 0.035); 32B QLoRA fits a 4090 at
seq_len 256 (smoke-proven). Nothing is packaged: no artifact anyone can pull.
**Increment:** GGUF-quantize the 14B + adapter, Ollama Modelfile, documented
serve/eval entrypoint. Multi-hour toolchain job (llama.cpp/Ollama not yet
installed in WSL; checkpoint and 948G disk are ready). Falsifier: a clean
machine pulls the artifact and reproduces the M7 easy-set receipts.

### 4. Second brain — kernel
wiki/feeds/intake/scout verify MATCH/DRIFT/UNVERIFIABLE on demand; no standing
observation layer.
**Increment:** `knowledge_monitor.py`, observe() + subscriptions + query API
over the sealed base. Falsifier: 3-node base where a changed source fires
exactly one drift subscription, fresh and unverifiable nodes classified
correctly, no false positives.

### 5. Compiler / PL (buildlang/buildc) — kernel
Strong theory (effects, linear types, dimensional analysis), one
production-grade backend (C), 612 passing cargo tests; the self-hosted
compiler and stdlib do not compile; no NL interface at all.
**Increment (parked until 1-3 land):** spec-driven NL-to-BuildLang generation
over the 8-program verified C-backend corpus, receipt-sealed per turn.
Falsifier: >=80% of the corpus regenerated from English passes the same
`buildc check` gate byte-identically on stdout.

### 6. Creative engine — kernel
Verification machinery exists (map_elites, mcts, transpile carriers); there is
no perceive/generate loop for open-ended work, no continuous critique, no
taste integration. ComfyUI-class tools are far ahead on features.
**Increment (parked):** structured creative search over a sealed design space
(parametric layout generation + rule-based local fitness + witnessed
receipts), an honest wedge rather than a diffusion-model chase.

### 7. Uplift engine — demo, deliberately last
The foundation is currently a negative result and stays that way until an
N>=100 hard set exists (single-shot <=50%), run at matched oracle budget with
a frontier baseline. Curation is the slow part; spread it across sessions and
do not run the eval early on a partial set.

## Sequencing

- **This session:** increment #1 (done, falsifier fired, suite green).
- **This week:** dataset receipt (#2); knowledge monitor (#4); begin N>=100
  hard-set curation (#7) as a background lane.
- **This month:** the packaging lane (#3, GGUF + Ollama + clean-machine
  falsifier); complete the N>=100 matched-budget ablation and publish the
  result whatever it is, including zero. That run decides whether the uplift
  engine is a flagship or a closed branch. Compiler and creative stay parked
  until the closure property and the packaged artifact have both shipped.

## The single biggest honesty risk

Re-asserting the retired +10%. It is the most quotable number the project ever
produced and it is unearned. Mechanism, not directive: the scorecards carry
UNEARNED in-repo, this file carries the quarantine rule, and any future lift
claim must arrive with the run that earned it.
