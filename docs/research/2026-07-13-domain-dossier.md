# The Domain Dossier — live-sourced, 2026-07-13

Method: twelve read-only research agents over four domains (learning, coding
agents, IDE experience, review of machine submissions), three modalities each
(arXiv-grade research 2025-2026, community sentiment weighted by engagement,
peer products verified from their own pages). Eleven of twelve returned; the
learning-domain sentiment agent hung and its slot is the one acknowledged
gap. Every claim below carries the URL it was fetched from. Nothing here is
from model memory.

## The one convergence

Every domain, every modality, the same finding: **verification, not
generation, is the bottleneck.** The METR randomized trial found experienced
maintainers 19% slower with AI while believing they were 20% faster
(https://arxiv.org/abs/2507.09089) — perception cannot gate acceptance.
Maintainers drown in plausible PRs; GitHub weighs a kill switch. Reviewers
wave through wrong code when complexity is high regardless of provenance
labels (https://dl.acm.org/doi/10.1145/3808165). The community's most
recurrent ask, across every thread cluster: make agent output cheap to
verify, keep the human driving, stop optimizing merge throughput.

This is the platform's home turf. The receipts architecture is not one
answer among several; it is the shape every research line independently
arrived at.

## Learning — the atrophy problem has mechanisms now

**Measured:** unrestricted AI use produced 77% failure on a later unaided
maintenance task vs 39% for gated use (explanation gates,
https://arxiv.org/abs/2602.20206); a 17-point comprehension hit for
AI-assisted juniors (https://www.infoq.com/news/2026/02/ai-coding-skill-formation/);
retention decays within a week after Copilot pairing
(https://arxiv.org/abs/2604.18538). Authorship-based knowledge metrics
(truck factor, git blame) are now invalid — the "substrate collapse"
(https://arxiv.org/abs/2606.20882).

**Peers:** learning is the empty quadrant. Cursor and Devin ship nothing.
Copilot gives students a price, not a different interaction model. Claude
Code's TODO(human) Learning style is the lone real mechanism and was demoted
to an opt-in plugin. The Socratic platforms (Boot.dev, Exercism/Jiki) own
the pedagogy but have no bridge into real repos.

**The builds this earns:**
1. **Explanation Gate** — an agent diff is accepted only after the user's
   own explanation of it passes an external check; the explanation + verdict
   is a comprehension receipt chained to the commit. Composes directly with
   the shipped attestation layer (coverage says what you walked; the gate
   says you understood it).
2. **Comprehension ledger** — per-module records of who last passed a
   verified understanding check, replacing git-blame ownership dashboards.
   The store + attestation entities are 80% of this.
3. **Retention receipts** — re-issue a variant of an accepted task days
   later; the unaided result is recorded, separating performance from
   durable learning (https://arxiv.org/abs/2605.15850 for timing policy).

## Coding agents — the checks must be external, adversarial, versioned

**Research:** a free agent inside a kernel-checked harness proved all 4,257
Iris core lemmas — acceptance decided solely by the Coq kernel, the proof
object as receipt (Aria, https://arxiv.org/abs/2607.06341; transfers to
Lean 4). Green tests are insufficient: adversarially induced patches pass
tests while embedding vulnerabilities at 0.91 success
(https://arxiv.org/abs/2509.25894). No fixed check survives growing agent
capability — checks must be versioned and co-evolve
(https://arxiv.org/abs/2606.26300). Self-logged agent trails are a trust
hole; the receiver should countersign (Sello,
https://arxiv.org/abs/2606.04193). Mid-run process monitors lift SWE-bench
resolution +10.6pp at ~$0.20/correction (https://arxiv.org/abs/2509.02360).

**Community (1,154 coded posts):** trust the harness less than the model —
hidden prompt overhead, silent regressions, non-authentic thinking. Revealed
preference: open auditable harnesses (the OpenCode thread), honest failure
reporting, small human-gated diffs, verification against explicit criteria.

**The builds this earns:**
4. **Versioned oracles** — every receipt records the hash of the check
   definition that accepted it, so old results can be re-adjudicated under
   stronger checks.
5. **Adversarial acceptance bundle** — green tests alone never accept; the
   receipted linter's security pass rides every agent accept path.
6. **Countersigned tool receipts** — the executor side already HMAC-signs
   results; chain those signatures into the store so the trail does not
   depend on the agent's honesty.
7. **Lean lane** — the apex oracle, one `elan` install away; Aria is the
   existence proof that agent + kernel-check is the strongest architecture.

## IDE experience — context is part of the result

**Research:** in-IDE quality is won by context packing, not model scale
(Mellum, https://arxiv.org/abs/2510.05788); ambient-signal context is
poisonable and invisible to developers (https://arxiv.org/html/2602.06759);
the 90-study review names verification overhead the central cost and
prescribes surfaced context, transparent explanations, user control
(https://arxiv.org/abs/2503.06195); developers oversee agents in four modes
and lean on test results as guarantees (https://arxiv.org/html/2606.05391v1).

**Community:** code-first surfaces over chat-first (the Cursor 3 backlash);
durable project context that agents do not forget; provider freedom and
local paths; no tool ever modifying output without consent (the Copilot
ad-injection and forced-trailer scandals were the two largest stories of
the half-year); predictable pricing.

**The builds this earns:**
8. **Context manifests** — every agent run and completion carries exactly
   which files/spans entered the window (the knowledge graph's context plan
   already computes this shape; attach it to run receipts).
9. **Time-to-verified-acceptance** as the north-star metric, logged in
   receipts — the METR result makes felt speed inadmissible.

## Review of machine submissions — from reading problem to evidence problem

**Research:** three-tier trust-calibrated review with risk-per-line scoring
(https://arxiv.org/abs/2606.01969); complexity, not provenance labels,
drives wrongful acceptance — surface complexity cues and demand stronger
receipts above thresholds (https://dl.acm.org/doi/10.1145/3808165); AI PRs
carry redundancy that reviewer sentiment masks
(https://arxiv.org/abs/2601.21276); trajectory review catches lucky passes
(AgentLens, https://arxiv.org/abs/2607.06624); line-level machine-readable
AI provenance is where OSS governance is heading (Agent-Trace,
https://arxiv.org/html/2603.26487); Cloudflare's production coordinator
verifies findings against source before reporting, 131k reviews/30 days at
$1.19 (https://blog.cloudflare.com/ai-code-review/).

**Peers:** all major reviewers are AI-reviewing-AI tuned for merge
throughput. Nobody distinguishes human from machine hunks inside one PR;
nobody binds review depth to provenance; quality metrics are
vendor-published; nothing connects the review moment to the reviewer's own
learning. GitHub alone has a structural gate (requester's approval does not
count).

**The builds this earns:**
10. **Risk-tiered run review** — extend the shipped run_review with
    per-hunk complexity and redundancy signals; above-threshold hunks
    demand a stronger receipt (tests, probe, or attestation at full
    coverage).
11. **Trajectory verdicts** — flag runs whose tests pass but whose process
    was unsound (edits after last green run already ship; add loop/rework
    scars to the acceptance surface).
12. **Line-level provenance** — Agent-Trace-shaped attribution in receipts:
    which hunks the model wrote, which the human wrote, bound to the
    conversation checkpoint.

## The build queue, ordered by leverage

| # | Build | Domain | Foundation already shipped |
|---|---|---|---|
| 1 | Explanation Gate + comprehension receipts | learning | attestation, run_review, store |
| 2 | Context manifests on run receipts | IDE | knowledge graph context plans |
| 3 | Risk-tiered run review (complexity + redundancy) | review | run_review, linter |
| 4 | Versioned oracles in receipts | agents | oracle, receipts |
| 5 | Countersigned tool receipts into the store | agents | tool_receipts HMAC, store |
| 6 | Comprehension ledger | learning | attestation entities |
| 7 | Line-level provenance (Agent-Trace shape) | review | ledger, diff machinery |
| 8 | Lean lane | agents/science | science_bench pattern |
| 9 | Retention receipts | learning | workflows, store |
| 10 | Time-to-verified-acceptance metric | IDE | router stats, receipts |

## Honest nulls and gaps

- The learning-domain community-sentiment slot is unfilled (hung agent);
  the adjacent domains' sentiment covered atrophy heavily, but the
  learner-community's own voice (students, bootcamps) was not directly
  sampled.
- Reddit could not be crawled directly by any agent; Reddit-specific
  sentiment is aggregator-mediated or absent, stated per-payload.
- One peer-survey claim (ACM complexity experiment) is abstract-level only,
  full text paywalled — marked moderate confidence at the source.
- Peer quality metrics (Bugbot 3x/10%, resolution rates) are
  vendor-published and independently unverified; treated as claims, not
  measurements, throughout.
