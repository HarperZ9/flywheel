# Research Curation — ninja_maths post + arXiv 2603.23420 + native integration

> Task origin: STATE.md 2026-07-09 (session 3, cont.), line 44-45 — "research
> curation (ninja_maths post + arXiv 2603.23420 + domain sweep) into native
> tool improvements," dispatched as an in-flight parallel-agent task. A prior
> attempt at this file hit ENOSPC (disk full) and left only a placeholder
> string ("placeholder-retry-2"). This is a fresh, from-source redo — no
> content below is recovered from a lost session; everything was re-verified
> against primary sources on 2026-07-09.

---

## 1. Source: arXiv 2603.23420

**Status: REACHABLE and VERIFIED** (confirmed via direct fetch of the arXiv
abstract page and the full HTML paper, not just search-engine summaries).

| Field | Value |
|---|---|
| Title | "Bilevel Autoresearch: Meta-Autoresearching Itself" |
| Authors | Yaonan Qu, Meng Lu |
| Venue | arXiv preprint, cs.AI — **not peer-reviewed** |
| Submission history | v1: 24 Mar 2026; v2: 2 Jun 2026 |
| Source | https://arxiv.org/abs/2603.23420 |
| Evidence grade | **LOW-MODERATE.** Real, dated, findable preprint (confirmed) with unusually honest self-disclosed limitations — but single-team, self-reported, statistically underpowered, toy-scale benchmark, no independent replication found. |

### Claimed mechanism
A bilevel framework: an inner autoresearch loop optimizes task performance; an
outer loop reads the inner loop's code and execution traces, identifies
bottlenecks, and synthesizes new search mechanisms (drawn from optimization,
bandits, design-of-experiments) *at runtime*, without explicit human
specification. Both loops use the same LLM — the paper's claimed gain is
attributed to the bilevel architecture, not a stronger meta-model.

### Adversarial read of the result (verified via direct fetch of the full paper, not the abstract)
- **Benchmark scale is small and narrow.** All results are on ONE task:
  nanoGPT-style GPT pretraining at 50M parameters, 300-second compute budget,
  single RTX 5090. The authors state generalization "to other model sizes,
  training budgets, or tasks is unproven" — direct quote from the paper.
- **Sample size is low and self-acknowledged as insufficient.** 3 independent
  repeats per group (12 runs across 4 groups). Direct quote: "Three repeats
  per group is insufficient for rigorous statistical comparison... Reliable
  estimates would require n>=10 repeats per group."
- **The headline "5x" number carries large relative error bars.** Group C
  (outer loop): -0.045 +/- 0.030 val_bpb vs. baseline Group A: -0.009 +/- 0.002
  val_bpb. A +/-0.030 error band on a -0.045 point estimate is ~67% relative
  uncertainty — the ratio is arithmetically consistent (0.045/0.009 = 5.0)
  but not statistically robust at n=3.
  - Confidence in the literal "5x" figure as a validated result: **LOW**.
  - Confidence that the paper is a real, honestly-reported preprint describing
    this mechanism and this (weak) evidence: **HIGH**.
- **Baseline absolute scale is small.** Baseline val_bpb ranges 1.094-1.114
  across repeats, uncontrolled; deltas of -0.009 to -0.045 are ~1-4% relative
  moves on that absolute scale — a small effect size even before the
  statistical-power caveat.
- **Compute-budget asymmetry, not fully controlled.** The outer loop adds
  ~3 minutes wall time and 4 additional LLM calls per session; the paper
  argues this doesn't affect inner-iteration counts but does not equalize
  wall-clock/compute spend between conditions in the headline comparison.
- **Nine explicit limitations disclosed in the paper's own Section 5.4**
  (small sample size, baseline variance, single benchmark, "carrier"
  limitation, recursive limitation, dynamic-load fragility, external-
  dependency exposure, prompt-induced domain bias, no stability guarantees).
  This level of self-disclosure is a positive signal for the paper's honesty,
  and a negative signal for citing the number as settled.
- No conflicts of interest are disclosed. No independent replication was
  found in this search pass. The paper states it "was primarily drafted by
  AI agents with human oversight and direction" — noted, not treated as
  disqualifying, but as a reason to weight the mechanism over the number.
- A secondary, unverified pointer surfaced in search results: a GitHub repo
  named `EdwardOptimization/Bilevel-Autoresearch`. **Not fetched or confirmed
  in this pass** — flagged as an unverified lead only, not used as evidence.

**Bottom line on this source:** the *mechanism* (introspect the inner loop's
code/traces, synthesize a new search strategy, re-run) is a legitimate,
reusable design pattern worth testing. The *specific 5x number* is not a
validated finding by any reasonable evidence bar and should not be quoted as
one.

---

## 2. Source: "ninja_maths" post

**Status: NOT RESOLVED — reported plainly per instruction, not papered over.**

- STATE.md records the task ("research curation... ninja_maths post...") but
  does not record which specific post, URL, or excerpt was intended. No file
  in the local-model repo (grepped across the full tree, scoped correctly to
  `C:\dev\local-model`) contains the string "ninja_maths," an arXiv id match
  other than 2603.23420, or any excerpt attributable to this handle. There is
  no recoverable prior-session artifact.
- The X/Twitter account **@ninja_maths** does exist and is identifiable via
  web search: "Alex Smith," described as chief content architect at
  Math Academy, ~15.6K followers, account since October 2010. This identity
  claim comes from search-engine summary text, not a page I fetched directly
  — direct confidence: **LOW-MODERATE** (plausible, not independently
  confirmed).
- **Direct fetch of the profile (`https://x.com/ninja_maths`) failed**: HTTP
  402 Payment Required. X/Twitter blocks unauthenticated scraping of profile
  timelines; I have no browser/authenticated-session tool available in this
  pass. This is an honest tooling gap, not a claim that no such post exists.
- Two candidate posts turned up via search (not confirmed as "the" post):
  one about "mapping the math genome" (curriculum-dependency structure), one
  about launching a "geometry-proof topics" curriculum. **Neither has an
  obvious connection to RL, verification, flywheels, search, or any
  native-tool-relevant mechanism** — on the harness's own `scout.py` triage
  vocabulary (relevant-AND-implies-a-falsifiable-extension = ACTIONABLE;
  relevant-but-metaphorical = INSPIRATION; else = NOISE), these two read as
  NOISE for this project: math-education curriculum content, no measurable
  mechanism (no knob, no metric, no ablation implied).

**Conclusion: the ninja_maths post is unreachable/unidentified in this pass.**
No integration claims are drawn from it below. If the intended post is a
specific URL, it needs to be supplied directly (X's paywall defeats blind
search-and-fetch).

---

## 3. INTEGRATION table (arXiv 2603.23420 mechanism only — nothing from ninja_maths, since that source was not resolved)

All "flywheel component" cells reference real, existing files in
`C:\dev\local-model\harness\`, confirmed present and read in this pass — not
assumed from memory.

| # | Finding (from the paper) | Flywheel component | Concrete native change | Effort |
|---|---|---|---|---|
| 1 | Outer loop introspects inner loop's code/traces to find bottlenecks and proposes new search mechanisms at runtime | `harness/evolve.py` (the meta-loop that already ranks `ImprovementCandidate`s from scout+telemetry by leverage x ease x falsifiability) | Add a new candidate source `"outer_loop"`: introspect `mcts.py`'s UCB1 selection stats and `map_elites.py`'s archive coverage, and emit a candidate proposing a search-mechanism parameter change (not a config auto-apply — keep it in the existing GATED lane, since it's a code/mechanism change, per evolve.py's own house rule) | Medium — new candidate source + tests; reuses existing rank/gate/apply plumbing, no new architecture |
| 2 | Gains attributed to the bilevel *architecture*, not a stronger model (same LLM both loops) | `harness/mcts.py` (M6 verifier-guided search, currently hardcoded UCB1) | Extract UCB1 selection into a pluggable strategy interface so alternate bandit/DOE selection rules can be swapped and A/B'd against the UCB1 baseline, using the same falsifier discipline M6 already applies (beats best-of-N only on dense-cheap-oracle-signal tasks) | Small-medium — refactor + comparison harness |
| 3 | Outer loop's core input is structured trace/bottleneck data, not raw logs | `harness/telemetry.py` -> `harness/evolve.py` | Extend telemetry to emit first-class "bottleneck" signals (cache-miss hotspot, oracle-latency hotspot) as `ImprovementCandidate` inputs — this literally closes one of the two open links `loop_closure.py` already names as unclosed (CONTENT altitude) | Small — schema extension + consumer wiring |
| 4 | Headline "5x" number is n=3, self-reported, single toy benchmark, author-acknowledged as statistically insufficient | N/A (methodology lesson, not a code target) | Log this source in the project's existing quarantine discipline (the same ledger that already holds the M7 "+10% UNEARNED" / ABLATION NEGATIVE precedent in STATE.md): record that the *mechanism* is worth testing via `scripts/run_ablation.py`-style methodology, but the *number* must never be cited as a validated benchmark or reused as a target | Trivial — documentation-only entry |
| 5 | Outer loop responds to stagnation/bottleneck signals with a mechanism swap | `harness/map_elites.py` + `harness/evolve.py` | A controller that watches MAP-Elites archive coverage/stagnation across flywheel cycles and proposes a mechanism swap (niche granularity, mutation operator) when stagnation is detected — same introspect-then-swap shape as the paper, attached to an existing component instead of invented fresh | Medium |

---

## 4. Do-not-integrate list

- **The literal "5x improvement" / "-0.045 vs -0.009 val_bpb" figure as a
  validated benchmark claim.** Single preprint, n=3 repeats, author-
  acknowledged as statistically insufficient, single 50M-param/300s-budget
  toy task, no independent replication. Citing this number as a target or
  proof point would directly repeat the mistake the project already made and
  already reversed once (M7's quarantined +10% claim, later shown to be
  ABLATION NEGATIVE — see STATE.md 2026-07-06 late entry).
- **Auto-apply of outer-loop-synthesized code/search-mechanism changes
  without the existing falsifier gate.** The paper's outer loop injects new
  search-mechanism code at runtime with no human specification. The
  project's own `evolve.py` deliberately keeps capability/code candidates
  GATED (never auto-applied) — its own docstring calls automating that
  "automates confusion." Porting the paper's more autonomous auto-injection
  wholesale would violate a house rule that exists on purpose; only the
  candidate-*proposal* half of the mechanism should be adopted, not the
  auto-apply half.
- **Anything from the ninja_maths post(s).** Not resolved (see Section 2).
  Nothing here is safe to integrate because the source itself is
  unconfirmed; forcing an integration item from an unverified/unidentified
  source would be exactly the fabrication this report is trying to avoid.
- **The unverified GitHub repo pointer** (`EdwardOptimization/Bilevel-
  Autoresearch`) — surfaced in search only, not fetched, not confirmed as
  the paper's own reference implementation. Do not treat any assumed contents
  of that repo as a source until it's actually read.

---

## 5. Top 5 integration candidates (ranked)

Ranked the same way `evolve.py` already ranks its own candidates: leverage x
ease x falsifiability.

1. **#3 — telemetry bottleneck signals -> evolve.py.** Smallest effort,
   directly closes a gap `loop_closure.py` already names as open (CONTENT
   altitude), easiest to falsifier-gate since it only adds a signal, not a
   new autonomous actor.
2. **#1 — evolve.py outer-loop candidate source.** Medium effort, most
   direct instantiation of the paper's actual mechanism, composes cleanly
   with the existing GATED lane instead of requiring a new one.
3. **#5 — map_elites stagnation-triggered mechanism swap.** Medium effort,
   attaches to a component that already exists for exactly this purpose
   (quality-diversity search), concrete stagnation metric available from the
   archive.
4. **#2 — mcts.py UCB1 -> pluggable strategy.** Moderate refactor effort;
   valuable mainly as the enabling step for #1/#5 to have something to swap
   *to*, so it is infrastructure rather than an end in itself.
5. **#4 — quarantine-ledger entry for the paper's own numbers.** Trivial
   build effort, but real value: protects the project from re-committing its
   own already-identified failure mode (asserting uplift from an
   underpowered, unreplicated result).

---

## 6. What is explicitly NOT claimed here

- No claim that any of the five integration ideas above have been built,
  tested, or falsifier-verified. This document is a curation + design-idea
  proposal, not a shipped change. Per this project's own discipline, code/
  mechanism changes stay GATED until a falsifier proves no regression.
- No claim about what the ninja_maths post says, argues, or implies for the
  flywheel — that source was not reached.
- No claim of independent replication for arXiv 2603.23420's numeric result.
- "Domain sweep" (the third item named alongside these two in STATE.md) is
  out of scope for this pass — not addressed here, not fabricated to fill
  the gap.
