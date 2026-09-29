<!-- writing-profile: readme -->
# Higher-order AI-tell detection and the regenerate loop

## The gap

The writing linter (`harness/writing_lint/`) scored prose clean on `per100w`
while human readers still read the same prose as machine-shaped. The reason is
where the tells live. The phrase engine in `check.py` reads vocabulary, and
`structural.py` reads a first layer of shape (rule of three, negative anaphora,
a short landing sentence). The tells that survive that pass live in higher-order
structure: the affirm-then-negate turn, parallel enumeration, the aphoristic
beat that seals a paragraph, one syntactic frame reused down a page, abstraction
with no concrete anchor, and a metronomic sentence cadence. A draft can carry all
six and still score `per100w = 0`.

This layer adds six report-only signals for those tells. Each operationalizes a
rule the STE writing standard already states, so this is not a new opinion about
prose. It is enforcement machinery for rules that were only prose before.

## Design constraint: report-only, never gate

The six signals are report-only. They never enter a profile's hard tuple, never
move the gated headline (`total`, `per100w`, `hard`), and never fail
`--gate`. Many processes depend on the gate, so the gate does not move. The
signals land on the same report-only surface as the existing passive-voice and
nominalization counts (`report_total`, `report_per100w`), plus a
`higher_order` detail block on the record that carries per-signal counts, spans,
and metrics.

Evidence that the gate is unchanged: gated `total`, `per100w`, `hard`, and
`em_dash` were compared against the pre-change linter across 70 (fixture x
profile) combinations spanning the open letter, a varied control, and twelve
real repository documents. Zero mismatches.

## The six signals and the rule each enforces

| Signal | STE rule it operationalizes |
| --- | --- |
| `corrective_negation` | No antithesis, no corrective negation, no contrasting pairs, no negative parallelisms |
| `parallel_enumeration` | No rule of three, no parataxis, no parallel structures within a paragraph |
| `aphoristic_landing` | No landing sentences, no summary beats, no setup-and-payoff |
| `repeated_syntactic_frame` | No throat-clearing openers, no reused sentence frames |
| `specificity_floor` | Numbers explain not impress. No receipt no accept. No unsourced authority |
| `rhythm_variance` | Vary sentence length unpredictably |

Each detector reports a count plus located spans or metrics:

1. **`corrective_negation`** (`higher_order.py`). Clause-level affirm-then-negate:
   `, not X`, `, never X`, `rather than`, `instead of`, and the `not X but Y`
   antithesis, plus adjacent-sentence mirror negation ("It proves X. It does not
   prove Y."), matched by a shared content stem. Flags any paragraph carrying two
   or more.
2. **`parallel_enumeration`** (`higher_order.py`). Comma or `and`/`or` runs of
   three or more short items whose head words share a part of speech (verb-led
   "price loans, read scans, flag threats" and noun-led "courts, agencies,
   hospitals, elections"). Reports run count, longest run, share of sentences
   with a run, and sub-flags three-item runs whose members are near-equal length.
3. **`aphoristic_landing`** (`higher_order.py`). A paragraph-final sentence that
   is shorter than the paragraph mean and either restates the opening (content
   stem overlap) or hits a tag phrase ("and that is the point", "is where the
   harm collects"). Reports the share of paragraphs ending on a landing beat, and
   a count of tag phrases anywhere.
4. **`repeated_syntactic_frame`** (`ho_frames.py`). Buckets sentences by opening
   template: pseudo-cleft ("What X is"), existential ("There is/are"), demonstrative
   copula, and leading function-word runs. Flags any template used three or more
   times, weighting pseudo-cleft openers highest.
5. **`specificity_floor`** (`ho_frames.py`). Concrete-anchor density (proper
   nouns, digits, dates, units, quotes) with a flag on anchorless paragraphs, plus
   an unsupported-claim scan: unsourced authority ("studies show", "a reviewer
   wrote", "recently"), unquantified magnitude ("tens of thousands", "many"), and
   a bare number with no adjacent denominator or interval.
6. **`rhythm_variance`** (`ho_frames.py`). Coefficient of variation and standard
   deviation of sentence word counts, the longest run of consecutive near-equal
   sentences, and the longest run of consecutive sentences sharing an opening part
   of speech. A low coefficient of variation or a long even run flags a
   metronomic cadence.

The coarse part-of-speech backbone shared by the detectors is in `ho_util.py`. It
is a shallow tagger, not a real one, which is acceptable because every reader of
it is report-only.

## Verification (open letter vs varied control)

Both scored under the `readme` profile. The gated headline is `0` for both. The
separation is entirely in the report-only detail.

| Signal | Open letter | Varied control |
| --- | --- | --- |
| `report_per100w` (all report-only) | 5.17 | 2.83 |
| `corrective_negation` (paragraphs flagged) | 7 (3) | 2 (0) |
| `parallel_enumeration` (runs, max items) | 4, 5 | 0, 0 |
| `aphoristic_landing` (tag hits) | 0 (4) | 0 (0) |
| `repeated_syntactic_frame` (weighted) | 5 (49) | 2 (10) |
| `rhythm_variance` (opening-POS run) | 1 (10) | 0 (2) |
| `specificity_floor` (anchorless, density) | 12 (8, 1.27) | 1 (1, 6.88) |

The letter shows the machine signatures: parallel enumeration, pseudo-cleft and
existential frames, an anchor density near a quarter of the control's, and a
ten-sentence run of the same opening part of speech. The control stays quiet.

## The generate-score-regenerate loop

The signals earn their keep by steering revision. The loop:

```
draft -> score -> plan -> regenerate (targeted spans) -> rescore
```

- **score** reads `check_text` and returns the record, gated and report.
- **plan** (`regen_loop.plan_targets`) maps each fired signal to a revision
  directive and the spans to touch. Targeted, not a full rewrite: raise
  specificity on the anchorless paragraphs, vary the metronomic runs, drop the
  antithesis at a span, break a balanced tricolon.
- **regenerate** rewrites only the flagged spans toward specificity, rhythm, and
  asymmetry.
- **rescore** confirms the signals cleared and the gated headline held.

### Scaffold status (this PR)

`harness/writing_lint/regen_loop.py` ships the deterministic stages. `score` and
`plan_targets` are real and tested. `run` is the control-flow skeleton.
`regenerate` is a caller-supplied seam, `regenerate(text, targets) -> text`. No
model is wired in this PR, so with no callback the loop scores once and returns
the plan, changing nothing. A follow-up wires the engine without redesigning the
loop.

### Honest-provenance principle (binding on any future wiring)

- The loop improves writing quality. A lower report score is a byproduct of
  clearer prose, never the target.
- The loop may attach a receipt of its edits (before and after report scores,
  which signals cleared), so the change is auditable.
- Disclosure of AI assistance stays with the end user and is never stripped.
- The loop never optimizes to defeat an AI detector. That is a non-goal.

## Honest nulls and known limits

- `aphoristic_landing` fired zero on the open letter under its strict condition
  (final sentence shorter than the paragraph mean). The letter's aphoristic
  closers ("and that is the point", "is where the harm collects") sit inside
  longer sentences, so the tag-phrase count surfaces them (4) while the
  paragraph-final flag does not. This is a real gap between the strict flag and
  the tag signature, kept visible rather than papered over.
- `parallel_enumeration` misses a list whose first item is glued to a long
  subject clause and whose last item is glued to the predicate with no comma. It
  catches the clear verb-led and noun-led runs.
- The part-of-speech backbone is a suffix-and-lexicon heuristic. It is
  report-only for that reason.
- These are English patterns. A clean result on non-English text means the
  English rules found nothing.
- This is quality diagnostics. It is not an AI-detector-evasion tool, and it must
  not become one.
