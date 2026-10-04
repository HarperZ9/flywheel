# Shapley placebo test

A placebo test for exact Shapley attribution over sources. It measures how often a
source that should get no credit gets credit anyway.

Shapley attribution over sources gives each source its average marginal effect on a
value function, across every coalition of the other sources. The value is exact for
its value function. A reader still needs to know whether the credits mean anything.
This feature mixes each real source with known-null controls, computes exact Shapley
values over all 2^N coalitions, and reports the false-attribution rate (FAR) over the
controls with Wilson 95% intervals. The verdict goes through `attribution_far.analyze`,
the same probe Flywheel uses for its other attribution methods.

## What it does

- `harness/shapley_far.py`: exact Shapley values for up to 10 sources in rational
  arithmetic, with an efficiency check per item. It turns each source's credit into a
  trial, reports FAR overall and per control kind, and adds gold detection on items
  the model can answer. It also reports "any credit", which counts negative credit too.
- `scripts/build_shapley_placebo_items.py`: builds items from public-domain passages.
  Each item has one gold passage that holds the answer and five controls: one empty
  source, two irrelevant passages, and two shuffled passages (an irrelevant passage's
  words in a seeded random order). The builder refuses a control that contains an
  accepted answer.
- `scripts/shapley_placebo_run.py`: starts its own `ollama serve` on a free loopback
  port, evaluates every coalition with greedy decoding, stops the server and its child
  processes by PID, and writes the full record. With `--gpu-lock DIR` it holds an
  owner-checked directory lock (`scripts/gpu_lock.py`) for the whole run.

## The preregistered run

The bar, the items, the value function and the model were fixed in
`project-docs/prereg/2026-10-04-shapley-placebo.md` and pushed before the run.

| Setting | Value |
|:--|:--|
| Model | Ollama `qwen2.5:7b`, manifest digest `845dbda0...0b697e`, Ollama 0.35.1 |
| Items | 16 questions over passages from Darwin's *The Voyage of the Beagle* (Gutenberg #944) |
| Sources per item | N = 6: one gold, five controls |
| Coalitions | 64 per item, 1,024 calls in all |
| Value function | 1 when the greedy answer contains an accepted answer as a whole word, else 0 |
| Credit threshold | a Shapley value above 0.05 |
| Bar | FAR at or below 0.05 (RELIABLE), and a Wilson upper bound at or below 0.10 for the claim "nulls rarely get credit here" |

**Result.**

| Measure | k / n | Rate | Wilson 95% |
|:--|:--|:--|:--|
| False attribution, all controls | 0 / 80 | 0.000 | 0.000 to 0.046 |
| Empty controls | 0 / 16 | 0.000 | 0.000 to 0.194 |
| Irrelevant controls | 0 / 32 | 0.000 | 0.000 to 0.107 |
| Shuffled controls | 0 / 32 | 0.000 | 0.000 to 0.107 |
| Any credit, positive or negative | 0 / 80 | 0.000 | 0.000 to 0.046 |
| Gold detection, answerable items | 16 / 16 | 1.000 | 0.806 to 1.000 |

Verdict: RELIABLE, and the upper bound (0.046) meets the preregistered 0.10.
All 16 items were answerable: the model failed every question with no sources and
answered every question with all six. The run took 127 seconds on one RTX 4090.

**How to read it.** In every item, v(S) was 1 exactly when the gold passage was in
S. That is a "dictator" game, so exact Shapley gave the gold source all the credit and
every control none. The test passed because, under this value function, this model
ignored these controls completely. A 0-or-1 value function cannot see a control that
shifts the model's confidence without flipping its answer. A graded value function,
such as the log-likelihood of the answer, could give the same controls nonzero
credit. This run does not measure that.

## Exploratory run: can this test fail?

Added after the primary result was read, recorded in the preregistration's deviations
section before this result was read, and not judged against the bar. Same items,
prompt, decoding and value function, on Ollama `qwen2.5:0.5b` (manifest digest
`a8b0c515...1827c67`). 1,024 calls, 52 seconds.

| Measure | k / n | Rate | Wilson 95% |
|:--|:--|:--|:--|
| False attribution, all controls | 7 / 80 | 0.088 | 0.043 to 0.170 |
| Empty controls | 1 / 16 | 0.063 | 0.011 to 0.283 |
| Irrelevant controls | 2 / 32 | 0.063 | 0.017 to 0.202 |
| Shuffled controls | 4 / 32 | 0.125 | 0.050 to 0.281 |
| Any credit, positive or negative | 25 / 80 | 0.313 | 0.222 to 0.421 |
| False attribution, answerable items only | 5 / 50 | 0.100 | 0.044 to 0.214 |
| Gold detection, answerable items | 10 / 10 | 1.000 | 0.722 to 1.000 |

The verdict would be UNRELIABLE. The smaller model's answers moved when an empty,
irrelevant or shuffled source was added, and exact Shapley passed those moves on as
credit, up to 0.13 for one shuffled source. Exact Shapley stays exact here. It
reports faithfully what the value function did, and the value function responded to
noise. So the test can fail, and it separates these two models on these items.

## Run it

```bash
python scripts/build_shapley_placebo_items.py --cache gutenberg --out items.json
python scripts/shapley_placebo_run.py --items items.json --out run.json \
  --model qwen2.5:7b --ollama "$(which ollama)" [--gpu-lock /path/to/gpu.lock.d]
```

The builder fetches six Project Gutenberg texts and records their SHA-256 values.
Gutenberg can change a file, so compare the item set's SHA-256 with the preregistered
one before comparing results. The committed item set and run record are in
`project-docs/records/2026-10-04-shapley-placebo/`.

## does_not_prove

- The rate covers these items, these control constructions, this model, this prompt
  and this value function only.
- It says nothing about attribution over pre-training data, LoRA-per-source methods,
  or hierarchical (grouped) attribution.
- It says nothing about N above 6, or about sampled Shapley estimators and their
  variance.
- It says nothing about a graded value function, where the same controls could earn
  credit.
- OpenMined's hosted Shapley demo uses a value function unknown here, so this run
  says nothing about it.
- The gold label is a construction: the answer string appears in that passage and in
  no control. It is not evidence about causes inside the model.
- A RELIABLE verdict shows the method rejected these placebos. It does not show the
  method is right on real attribution questions.

## Licences and sources

The passages are from Project Gutenberg texts that are public domain in the United
States: #944 (Darwin), #2701 (Melville), #1228 (Darwin), #205 (Thoreau), #308 (Jerome)
and #201 (Abbott). The Shapley value is Lloyd Shapley's 1953 construction; nothing is
vendored.
