# Preregistration: a placebo test for exact Shapley attribution over sources

**Prereg id:** `prereg.shapley-placebo.v1`
**Frozen:** by the commit that adds this file. Nothing scored runs before that
commit exists. The run record names this commit.
**Register:** internal. The feature page `docs/features/shapley-placebo.md` is
downstream of it.

## 0. The question

Exact Shapley attribution over sources gives each source its average marginal
effect on a value function across every coalition of the other sources. A reader
who sees "source C earned 0.4 of the credit" needs to know how often a source that
should earn nothing earns credit anyway. This run measures that rate on a small
local setup with known-null controls.

## 1. Fixed inputs

| Input | Value |
|:--|:--|
| Item set | `project-docs/records/2026-10-04-shapley-placebo/items-v1.json`, sha256 `11f7f0e2c118c7c1b185e5b29bf6c4162743085e8f2a0feaee26de2446bfa719` |
| Item builder | `scripts/build_shapley_placebo_items.py`, seed 20261004 |
| Scoring module | `harness/shapley_far.py`, sha256 `1917f8ed677968322ac9c889d80834ae5d660cca08ecb3030518fba46b4feca3` |
| Run script | `scripts/shapley_placebo_run.py`, sha256 `1a63afe7aa3fd7657737b93cd620a323c912c740fe0ccd5b1bdd39ba001582f6` |
| Model | Ollama `qwen2.5:7b`, manifest digest `845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e` |
| Decoding | temperature 0, seed 0, `num_predict` 24, `num_ctx` 4096 |

**Items.** 16 questions. Each answer appears in exactly one gold passage from
Darwin's *The Voyage of the Beagle* (Project Gutenberg #944). Each item has N = 6
sources in a seeded random order: the gold passage and five known-null controls.

- one **empty** source;
- two **irrelevant** passages from other public-domain books (Gutenberg #2701,
  #1228, #205, #308, #201), with no digits and no accepted answer as a whole word;
- two **shuffled** sources: the words of such a passage in a seeded random order.

**Value function** (`greedy-answer-contains-accepted/1`). For a coalition S, the
model answers the question from the prompt `sources-then-question/1` with only the
sources in S. v(S) = 1 when the normalized answer contains an accepted answer as a
whole word, else 0. Each source keeps its letter in every coalition.

**Attribution.** Exact Shapley values over all 2^6 = 64 coalitions per item,
computed in rational arithmetic. Efficiency, sum of values = v(all) - v(empty set),
is checked per item; a failure stops the run.

## 2. Primary measure and bar

- **Trial.** One (item, control source) pair: 16 x 5 = 80 control trials.
- **False attribution.** A control's Shapley value is above the credit threshold
  1/20 = 0.05.
- **False-attribution rate (FAR).** False attributions over control trials, with a
  Wilson 95% interval.
- **Bar.** The verdict is `attribution_far.analyze` with its default threshold:
  RELIABLE when FAR is at or below 0.05, else UNRELIABLE. The claim "nulls rarely
  get credit in this setup" additionally needs the Wilson upper bound at or below
  0.10. If the point estimate passes and the upper bound does not, the report says
  the sample cannot support that claim.

## 3. Secondary measures, reported whatever they show

1. FAR per control kind (empty, irrelevant, shuffled), each with a Wilson interval.
2. Any credit: |value| above 0.05, which also counts negative credit.
3. FAR restricted to answerable items, where v(all) = 1 and v(empty set) = 0.
4. Gold detection on answerable items: the gold source's value above 0.05.
5. Calls and wall time per item.

## 4. What would change a decision

If FAR is above 0.05, Flywheel's docs say exact Shapley over sources needs a
placebo control before any credit is shown to a user, and this setup's numbers go
in that sentence. If FAR is at or below 0.05 with an upper bound at or below 0.10,
the docs say this setup passed its placebo test, and name its limits.

## 5. What this run cannot show

- Anything about attribution over pre-training data, LoRA-per-source methods or
  hierarchical (grouped) attribution.
- Behavior beyond N = 6, or of sampled Shapley estimators.
- Behavior under another value function, such as answer log-likelihood or a
  judge score. A different value function can give different credits.
- Anything about OpenMined's hosted Shapley demo, whose value function is unknown
  here.
- Whether the gold passage is the "true" cause of a correct answer in any deeper
  sense. The gold label is a construction: the answer string is in that passage
  and in no control.

## 6. Deviations

Any change after the freeze is recorded here, dated, with the reason, before the
result is read.

- **2026-10-03 (session clock), after the primary result was read.** The primary run
  gave v(S) = 1 exactly when the gold passage was in S, for all 16 items, so every
  control earned zero credit. That leaves open whether this test can fail at all. One
  exploratory run on Ollama `qwen2.5:0.5b`, same items, prompt, decoding and value
  function, is added to find out. It is labeled exploratory, is not judged against the
  bar in section 2, and does not change the primary verdict. Recorded before its
  result was read.
