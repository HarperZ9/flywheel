# Learning academy: domain dossier (2026-07-14)

Method: every finding below was adversarially re-checked against its source;
the claim text was matched to the source's own words and numbers. Seven
findings survived checking. Nine failed and were dropped. Nulls are
first-class content here, not footnotes.

## 1. The frontier in five sentences

By mid-2026 the AI-tutoring literature has real RCTs, and they agree on one
split: carefully designed, guardrailed tutors produce measurable gains on
proximal tests, while raw chatbot access can actively harm unassisted
performance (https://www.nature.com/articles/s41598-025-97652-6, 2025-06-03;
https://www.pnas.org/doi/10.1073/pnas.2422633122, 2025). The strongest
supervised result so far has AI drafts matching human tutors across five UK
schools with 76.4% of drafts approved with zero or minimal edits (high
confidence, https://arxiv.org/abs/2512.23633, 2025-12-29), which is a
human-approval gate producing a measurable approval rate, exactly the shape a
witnessed platform records. The cognitive-science base underneath is weaker
than its reputation: classroom spacing effects run roughly d = 0.54 against
lab-derived priors near 0.85 (high confidence,
https://pmc.ncbi.nlm.nih.gov/articles/PMC12189222/, 2025-06-03), and retrieval
practice for mathematics has no confirmed effect at all
(https://link.springer.com/article/10.1007/s10648-025-10035-1, 2025-07-29).
Deskilling now has its first patient-outcome evidence, a 6.0 percentage-point
drop in non-assisted colonoscopy detection after routine AI introduction
(https://www.thelancet.com/journals/langas/article/PIIS2468-1253(25)00133-5/fulltext,
August 2025), but no study has yet measured durable retention from AI tutoring
or skill decay in software developers. The domain's open gap is therefore
measurement itself: assisted-practice numbers, immediate post-tests, and
lab priors all systematically overstate what learners keep, and a
verified-inference platform is the tool built to refuse those overstatements.

## 2. Confirmed findings

### F1. A purpose-built AI tutor beat Harvard's active-learning classroom

Claim: in a crossover RCT (n = 194, Harvard intro physics), students using a
research-based AI tutor showed learning gains over double those of the
in-class active-learning condition; effect size 0.63 SD by linear regression
and 0.73 to 1.3 SD under ceiling-adjusted quantile regression (z = -5.6,
p < 10^-8), with median time on task 49 minutes against an assumed 60 in
class (all figures high confidence, verified against the article page).

Source: Kestin et al., Scientific Reports 15:17458,
https://www.nature.com/articles/s41598-025-97652-6, published 2025-06-03.

Why it matters: the effect came from expert-authored scaffolds and guardrails,
not from raw model access. The pedagogy contract is the active ingredient,
and a contract is exactly the kind of artifact a verified-inference platform
can pin, version, and emit receipts against, instead of shipping an
unauditable prompt.

Pour-back: `BATTLE-MAP.md` learning-academy lane. Shape: a tutor profile is a
committed, hash-pinned pedagogy contract (scaffold set plus guardrail rules),
and every tutoring session receipt references the contract hash it ran under.

### F2. Assisted gains and unassisted outcomes diverge, hard

Claim: in an RCT with roughly 1,000 Turkish high-school students, raw GPT-4
access improved assisted practice performance by 48% but reduced unassisted
exam scores by 17% versus never-had-access; a guardrailed GPT Tutor improved
assisted practice by 127% and largely eliminated the exam harm, without
producing exam gains (all figures high confidence from abstract records; a
published correction exists and leaves these numbers unchanged).

Source: Bastani et al., PNAS 122(26):e2422633122,
https://www.pnas.org/doi/10.1073/pnas.2422633122, 2025 (URL constructed from
the DOI, moderate confidence; the publisher page blocks automated fetch).

Why it matters: this is the domain's central measurement trap. Any learning
product that reports assisted-practice metrics is reporting the one number
this study shows can move +48% while the outcome that matters moves -17%.
A verified-inference platform should make the assisted/unassisted split a
schema-level distinction, so the misleading aggregate cannot be emitted.

Pour-back: `harness/` eval receipt schema. Shape: two mandatory, separately
named metric channels (`assisted_practice`, `unassisted_posttest`); any
uplift claim that cites only the assisted channel fails the claim gate.

### F3. Routine AI assistance measurably eroded unassisted clinician skill

Claim: across four Polish ACCEPT-trial centres, the adenoma detection rate of
standard non-AI colonoscopy fell from 28.4% (226/795) to 22.4% (145/648)
after routine AI introduction, an absolute difference of -6.0 percentage
points; this is the first patient-outcome deskilling evidence (figures high
confidence, matched across the press release, the linked Lancet commentary,
and clinical coverage).

Source: Budzyn et al., The Lancet Gastroenterology & Hepatology,
https://www.thelancet.com/journals/langas/article/PIIS2468-1253(25)00133-5/fulltext,
published online August 2025.

Why it matters: it is observational and from another domain, but it is the
strongest signal yet that always-on assistance degrades the unassisted
skill underneath it. For a platform whose thesis is work trustworthy enough
to walk away from, periodic unassisted operation is a measurable property,
not a philosophy.

Pour-back: learning-academy spec in `docs/`. Shape: an unassisted-mode
cadence (scheduled sessions with assistance off, results logged to the same
receipt stream) so skill retention has a time series instead of an anecdote.

### F4. For mathematics, spacing is real and small; retrieval is unproven

Claim: meta-analysis of mathematics learning found spaced versus massed
practice at g = 0.28 across 27 studies and 53 effect sizes, dropping to
g = 0.24 when course-embedded; testing versus restudy across 7 studies and
32 effect sizes gave g = 0.18 with a 95% CI crossing zero (all figures high
confidence, verified against the article page).

Source: Educational Psychology Review 37:75,
https://link.springer.com/article/10.1007/s10648-025-10035-1, published
2025-07-29.

Why it matters: procedural and problem-solving content is closest to what a
coding-focused platform would teach, and the two most-cited learning
techniques perform very differently there. Honest priors per content type
belong in the product's claims, not in a citation nobody re-reads.

Pour-back: scheduler priors table in `docs/` (consumed by any future
`harness/` scheduler). Shape: per-technique, per-content-type expected-effect
rows with source URL and CI, where the retrieval-for-math row is an explicit
null.

### F5. Classroom spacing has usable defaults: 7-day gaps, at most 3 re-exposures

Claim: classroom distributed-practice meta-analysis (22 reports, 31 effect
sizes, N > 3,000) found d = 0.54, 95% CI [0.31, 0.77], with I2 = 92.13%;
fixed 7-day intervals were the most consistently positive schedule and three
re-exposures after initial learning carried the significant effects; the
prior lab-plus-applied combined estimate of d = 0.85 overstates the classroom
effect (all figures high confidence, verified against the article).

Source: https://pmc.ncbi.nlm.nih.gov/articles/PMC12189222/, published
2025-06-03.

Why it matters: this is one of the few findings in the domain that compiles
directly to code: a 7-day fixed interval, a cap of three re-exposures, and a
classroom-grade prior for the expected lift. The I2 of 92% also means the
effect varies enough that each deployment must measure its own lift, which
is what a receipts platform does by default.

Pour-back: `BATTLE-MAP.md` learning-academy lane plus a scheduler module
under `harness/`. Shape: scheduler defaults set to the classroom numbers,
and a measured-lift receipt per deployment rather than an inherited prior.

### F6. Augmenting the human tutor is cheap and helps weakest tutors most

Claim: in the Tutor CoPilot RCT (900 tutors, 1,800 K-12 students), students
of assisted tutors were 4 percentage points more likely to master topics
(p < 0.01), rising to 9 points for students of the lowest-rated tutors, at
about $20 per tutor per year; assisted tutors asked more guiding questions
and gave away answers less (all figures high confidence, verified against
the arXiv abstract).

Source: Wang et al., https://arxiv.org/abs/2410.03017, submitted 2024-10-03.

Why it matters: the gains concentrate where skill is lowest and the
mechanism is behavioral (question-asking up, answer-giving down), which is
directly classifiable per turn. A platform can witness the mechanism, not
just the outcome: each tutor turn carries a machine-checkable label.

Pour-back: `dataset/` task family plus `harness/` scorer. Shape: a labeled
fixture set of tutor turns (guiding question versus answer giveaway) and a
scorer that emits the per-session ratio into the receipt.

### F7. Supervised AI tutoring matched human tutors under a human-approval gate

Claim: an exploratory RCT (n = 165, five UK secondary schools) found students
tutored by supervised LearnLM performed at least as well as human-tutored
students on all measured outcomes and were 5.5 points more likely to solve
novel problems (66.2% versus 60.7%); supervising tutors approved 76.4% of AI
draft messages with zero or minimal edits (all figures high confidence,
verified against the arXiv abstract).

Source: https://arxiv.org/abs/2512.23633, submitted 2025-12-29.

Why it matters: this is the draft-approve-send loop with published gate
metrics. The 76.4% approval rate is precisely the kind of number a witnessed
gate ledger produces for free, and it turns "human in the loop" from a
slogan into a rate with a denominator.

Pour-back: gate ledger spec in `docs/`. Shape: per-draft approval outcome
(approved as-is, minimal edit, rewritten, rejected) logged with the draft
hash, so any deployment can publish its own approval-rate table.

## 3. Honest nulls

- Retrieval practice has NOT been shown to work for mathematics: the July
  2025 Educational Psychology Review meta-analysis found g = 0.18 with a 95%
  CI crossing zero (7 studies), so the testing effect cannot be assumed for
  procedural or problem-solving content
  (https://link.springer.com/article/10.1007/s10648-025-10035-1, 2025-07-29).
- Even guardrailed AI tutoring did not raise unassisted exam scores in the
  Bastani PNAS RCT. The GPT Tutor arm only neutralized the -17% harm seen
  with raw GPT-4; no arm beat the no-AI control on the closed-book exam
  (https://www.pnas.org/doi/10.1073/pnas.2422633122, 2025).
- No named 2024-2026 AI-tutoring RCT has measured durable long-term
  retention: Harvard and Nigeria both used immediate or near-term post-tests,
  and the World Bank explicitly states long-term effects are unknown; the
  Nigeria "2 years of learning in 6 weeks" line is a blog-level conversion of
  0.3 SD that was not yet peer-reviewed at publication
  (https://blogs.worldbank.org/en/education/From-chalkboards-to-chatbots-Transforming-learning-in-Nigeria,
  2025-01-09, moderate confidence on the exact post URL).
- Classroom spacing effects are roughly 35-60% smaller than lab-derived
  numbers (d = 0.54 classroom versus d of about 0.85 in combined estimates)
  with I2 = 92% heterogeneity, so lab effect sizes must not be used as the
  expected-lift prior
  (https://pmc.ncbi.nlm.nih.gov/articles/PMC12189222/, 2025-06-03).
- The MIT "cognitive debt" study is a non-peer-reviewed preprint with n = 54
  (n = 18 in the critical fourth session); its EEG claims are widely
  over-cited relative to its evidence and should be used only as a source of
  cheap instruments (the quote-your-own-work probe), not as proof of neural
  harm (https://arxiv.org/abs/2506.08872, 2025-06-10).
- There is still no direct RCT showing long-term skill decay in software
  developers from Copilot-style pairing; the deskilling evidence base is
  domain-transfer only (colonoscopy ADR drop, essay-writing recall), so a
  Flywheel claim about coding-skill decay would currently be unsupported.

## 4. Dropped in verification

Nine findings failed adversarial checking against their claimed sources and
were dropped; they are not reproduced here.

## 5. Build candidates

### B1. Assisted/unassisted metric split in the eval receipt

The Bastani divergence (F2) as a schema rule: no learning-related receipt may
report a single blended score. Pour-back target: `harness/` receipt schema.
Smallest committable first slice: add `assisted_practice` and
`unassisted_posttest` as distinct schema fields with a validator that rejects
uplift claims citing only the assisted channel, plus one fixture test for the
rejection path.

### B2. Spacing scheduler with classroom priors

F5 compiled to code: fixed 7-day review intervals, a cap of three
re-exposures, expected lift documented at the classroom d = 0.54, not the lab
0.85, and the retrieval-for-math null recorded so the scheduler never claims
a testing effect for math content. Pour-back target: `harness/` module plus
`BATTLE-MAP.md` lane entry. Smallest committable first slice: a pure
scheduler module that maps an item-history log to a dated review queue, with
unit tests for interval and cap behavior and a priors table in its docstring
citing both sources.

### B3. Tutor-turn behavior scorer (guiding question versus answer giveaway)

The Tutor CoPilot mechanism (F6) as a witnessed metric: classify each tutor
turn and emit the per-session ratio into the receipt, making the behavioral
contract of F1 checkable. Pour-back target: `dataset/` fixture family plus a
`harness/` scorer. Smallest committable first slice: 30 to 50 hand-labeled
tutor turns committed as fixtures plus a scorer script whose accuracy on the
fixtures is asserted in a test.

### B4. Quote-your-own-work retention probe

The one salvageable instrument from the MIT preprint (per the null): after a
session, probe whether the learner can reproduce a key line of their own
output, and log pass/fail into the receipt stream as a cheap retention
signal, claimed as an instrument and never as evidence of neural effects.
Pour-back target: learning-academy spec in `docs/` plus a probe template.
Smallest committable first slice: the probe prompt template, its scoring rule
(exact-substring versus paraphrase threshold), and the receipt field it
writes, committed as a spec with two worked examples.
