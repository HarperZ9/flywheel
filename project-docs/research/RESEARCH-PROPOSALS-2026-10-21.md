# Research proposals, 21 October 2026

Flywheel matures before it gains new capability. Three items from this batch closed
gaps in what Flywheel already claims and shipped in the same change as this note:
runtime identity in eval receipts and the config hash, an access statement in eval
receipts, and 16 partial-check false accepts in the corpus. The items below are
proposals. None is started. Each names its source, a target and the result that
would sink it. Every peer number comes from the peer and was not re-run here. Most
sources were read in part, so numbers carry moderate confidence until checked
against the papers.

## Maturity, next in line

### Cost per verified task, team against solo
- Source: Cohere, "Lessons from scaling teams of frontier coding agents" (2026-10-14).
  A planning-only async team scored 63.6% for $249 against 63.2% for $510, and teams
  cost 3 to 7 times as much as solo runs. Cohere says non-GPT results are single runs.
- Target: fan-in and parity reports show cost per verified task beside pass rate,
  with a paired per-task interval against a solo arm on the same tasks; token prices
  carry a source and a date. Merge with the paired-config runner proposal of
  15 October.
- Sinks it: a team configuration reported as better while its cost-adjusted interval
  includes the solo arm.

## New capability

### Observer-effect check for activation capture
- Sources: SauersML, `watching` (github.com/SauersML/watching); LawZero, Fornasiere
  et al., "Language models recognize dropout and Gaussian noise applied to their
  activations" (2026-05-13).
- Target: when a run attaches capture hooks, run a fixed 64-prompt set with capture
  on and off, and record the share of changed tokens and logits in the receipt. A
  finding from internal signals is UNVERIFIABLE when that share is above zero and no
  eager control exists. Needs a local model and a free GPU.
- Sinks it: the check reports zero change on a compiled-capture setup known to shift
  logits.

### Update-aware reasoning as a trace observation
- Source: Apollo Research, Hojmark and Newman, "GLM-5.3 sometimes considers how
  train-time actions shape future behavior" (2026-10-15). 10 of 6,452 rollouts were
  flagged; reasoning length is a named confounder.
- Target: an `update_aware` category beside `eval_awareness`, with the rate per
  rollout and per 1,000 reasoning tokens and an exact interval. The grader's flag is
  a covariate and never accepts.
- Sinks it: the per-token rate ranks models differently from the per-rollout rate on
  the same data; then the per-rollout number cannot be shown alone.

### Claim-to-receipt map for generated reports
- Source: Lange et al., "The Agentic Scientist", arXiv 2610.18933. The model
  reviewer's score correlated with measured performance at r = 0.44.
- Target: `flywheel check report.md` resolves each number and named result in a
  report to a receipt field and returns MATCH, DRIFT or UNVERIFIABLE per claim.
  Catch at least 19 of 20 planted wrong numbers, with 0 false DRIFT on 20 clean
  reports.
- Sinks it: planted errors written as prose ("about half") slip past extraction;
  report that class separately.

### Interval coverage witness
- Sources: Cloudflare, "Introducing Clairic" (2026-10-19): 17 of 21 actuals inside
  an 80% interval. DeepMind `regress-lm` README.
- Target: count held-out actuals inside each emitted interval and return DRIFT when
  coverage falls outside a binomial band around nominal; report n, and UNVERIFIABLE
  when n is too small for the band to exclude anything.

### Rewind-task lane
- Sources: Rohan Arun, posts of 2026-10-14 and 2026-10-15, and the
  `Auto-research-agent` README, which itself declines a causal claim.
- Target: at least 30 tasks from public research repos pinned at a past commit and
  scored by the later commit's evaluator, run as paired arms through the McNemar
  planner, with a contamination field (web search, model cutoff against solution
  date). Build it as the second task source of the paired-config runner.
- Sinks it: contamination cannot be ruled out; that task reports UNVERIFIABLE.

### Program-search lane with a deterministic accept
- Source: Gu, Kemeny, Yelin, Lukin, "Discovering state-of-the-art quantum circuits
  with large language models", arXiv 2610.22367. Only the abstract was read.
- Target: first a docs example of a learned proposer with an executable accept, once
  the paper's verification section is read; later a `program_search` lane where
  candidates enter only through an executable checker and the score is sealed.
- Sinks it: the paper's evaluator rests on a learned component.

## Watch

- InfiLoop, arXiv 2610.11570: more loop iterations can overwrite correct states. For
  test-time scaling sweeps, report accuracy at every step.
- Leo Gao, "Neural networks are not already clean" (2026-10-17): score a neuron
  explanation by downstream KL of a simulated replacement. Relevant only if Flywheel
  accepts interpretability claims; his ablation results are not yet posted.

## Does not prove

These sources show what one reader looked at in one week, not what Flywheel users
need. "Not present in Flywheel" comes from searches of one revision of main.
