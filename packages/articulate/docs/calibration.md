# Calibration

The detector's rules and tiers are pinned: `scripts/check_release_ruleset.py`
fails a release if one byte of the rule closure changes. When evidence shows a
tier harms a group of writers, the correction lives in a separate layer that
runs after the detector and before the gate. That layer is
`articulate.calibration`, and this page is its decision record.

## What calibration/1 changes

| Finding | Before | After | Why |
|:-|:-|:-|:-|
| `filler-intensifier` (the four intensifier words) | HIGH, blocks under the default profile | LOW, reported with the label prefix `report only:` | It blocked learner writing at ten times the per-word rate of native writing |
| A HIGH or MEDIUM finding wholly inside an attributed quotation | blocks | LOW, label prefix `quoted:` | The words belong to the person quoted |

No finding is removed. A moved finding still shows in every report, so the
writer still sees it. A profile that wants the intensifier rule to block names
it in `gate_promote`.

A quotation counts as attributed when a speech or citation verb sits within
the 60 characters before it or the 40 after it (`said`, `wrote`, `argued`,
`according to` and similar) and the quotation is under 60% of its paragraph.
Quotation marks around one's own paragraph change nothing, and a quotation with
no attribution is left alone.

## The evidence

The September audit ran Articulate 0.4.1 on the Liang et al. (2023) essays. It
found that `filler-intensifier` fires on 26 of 91 TOEFL learner texts and on 2
of 70 length-matched windows of US college essays. The pooled per-word ratio is
10.6, and the bootstrap 95% interval runs from 3.8 upward. The ruleset has
the same fingerprint in 0.16.0, `sha256:9f78a7484bb20f84`, and a re-run gives
the same counts.

## How the fix was chosen

Four options were scored by `scripts/fairness_filler_options.py`. Each one
re-tiers the detector's own findings, so no rule or text changes.

| Option | What it does |
|:-|:-|
| baseline | as shipped |
| demote | every intensifier finding moves to LOW |
| split | two of the four words move to LOW; the two that the GPT-4 rewrites in the study favoured stay HIGH |
| density | the finding blocks only at 10 or more intensifiers per 1,000 words |

The choice rule was written into the script before any held-out number was
read. On the tuning half (even-indexed documents), take the option with the
smallest TOEFL minus college blocked-rate difference, among options that lower
the blocked rate on AI documents of the known-provenance corpus by 2 points or
less. Ties go to the option that keeps more findings blocking.

On the tuning half, demote and split tied, and demote came first in the list.
The tie-break did not separate them, because it counted only sets where the two
options agree. A tie-break that looked at the GPT-4 rewrites would have chosen
split. Those rewrites were declared report-only before the run, so the rule as
written stands, and split is recorded here as the documented alternative.

Default-profile blocked rates on the held-out half (odd-indexed documents):

| Option | TOEFL | College windows | Difference [95%] |
|:-|-:|-:|:-|
| baseline | 20/45 | 7/35 | +0.24 [+0.04, +0.42] |
| demote | 9/45 | 7/35 | 0.00 [-0.18, +0.17] |
| split | 9/45 | 7/35 | 0.00 [-0.18, +0.17] |
| density | 15/45 | 7/35 | +0.13 [-0.07, +0.31] |

## The shipped layer, measured

`scripts/fairness_calibration_check.py` runs the real `check` path with the
layer off and on. Results are in
`corpus/core-devices/calibration-check-2026-10-26.json`.

| Set | n | Blocked before | Blocked after |
|:-|-:|-:|-:|
| TOEFL learner essays | 91 | 38 | 14 |
| US college essay windows | 70 | 21 | 20 |
| Student abstract windows | 145 | 31 | 27 |
| PERSUADE English learners | 18 | 8 | 5 |
| PERSUADE other students | 36 | 20 | 11 |
| Known-provenance human texts | 75 | 40 | 25 |
| Known-provenance AI texts | 84 | 71 | 71 |
| TOEFL texts after the GPT-4 rewrite | 91 | 25 | 15 |
| ChatGPT college essay windows | 31 | 9 | 4 |
| ChatGPT abstract windows | 145 | 19 | 19 |

TOEFL minus college blocked rate moves from +0.12 [-0.03, +0.26] to
-0.13 [-0.26, -0.00]. TOEFL minus abstracts moves from +0.20 [+0.08, +0.32] to
-0.03 [-0.13, +0.07]. The PERSUADE learner gap was inside its interval before
and after.

**The cost.** The rule also blocked some machine text: 10 of the GPT-4
rewrites and 5 of the ChatGPT essay windows stop blocking. Recall on the 84 AI
texts of the provenance corpus does not move. The finding still shows on all of
them as a LOW advisory.

## Weights: measured and unmeasured

| Weight | Status | Reason |
|:-|:-|:-|
| `filler-intensifier` tier | measured, calibration/1 | the fairness evidence above |
| Quotation attribution window (60 and 40 characters, 60% share) | unmeasured | set by hand; no labelled quotation set exists yet |
| Device reader thresholds (`docs/devices.md`) | tuned on the dev split, measured on two held-out splits | see that page |
| Graded survival rules (`articulate.survival`) | unmeasured | fixed rules; no reader judgments to calibrate against |
| All other detector tiers | unmeasured | pinned ruleset; tiers set by hand |
| Texture-score coefficients and the cut at 30 | unmeasured | pinned; the only labelled data is the provenance corpus, whose README forbids choosing a threshold from it, and its time gap confounds period style with authorship |
| Cadence thresholds | unmeasured | pinned; the audit found uniform cadence fires on 12 of 91 TOEFL texts and 1 of 70 college windows, and it never enters the verdict |
| The 30-word verdict floor | unmeasured | pinned |
| Negation-load cuts | unmeasured | no labelled set |
| Dialogue checks | measured | calibrated on public-domain plays (`docs/dialogue-calibration.json`) |

## Receipts

A receipt names `calibration` when the layer moved a finding in its text, and
`articulate verify` replays it under that version. A receipt made before the
layer existed carries no such field and replays without the layer, so it still
reads Match. A receipt that names an unknown version reads Unverifiable.

## Limits

- The Liang TOEFL texts are probably transcripts of spoken answers, and the
  study's US eighth-grade arm has no text in the local copy. Whether young
  native writers use the intensifiers at learner rates is still unknown.
- 18 PERSUADE learners give wide intervals.
- The choice was made by the person who built the layer. The rule was fixed
  before the held-out numbers, and the tie is reported as it fell.
