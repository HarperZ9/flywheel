# Known-provenance corpus

This corpus is the baseline for measuring Articulate's bench call. Every
document has a known origin: a human wrote it, a local model generated it, or
a local model edited a human text. `manifest.json` lists each document with
its SHA-256, its class, its genre and how it came to exist. Binoculars and
Fast-DetectGPT run on the same documents as outside comparison points.

No rule, gate, threshold or editor setting is chosen from these results.
They measure Articulate as it stands.

## What is in it

| Class | Genre | Count | Source | Where the text lives |
|:-|:-|-:|:-|:-|
| human | fiction | 9 | Melville, Abbott and Jerome, 1851 to 1889 | `human/`, committed |
| human | essay | 3 | Thoreau, *Walden*, 1854 | `human/`, committed |
| human | science | 6 | Darwin, 1839 and 1859 | `human/`, committed |
| human | speech | 3 | Declaration preamble, two Lincoln speeches | `../human/`, committed |
| human | student essay | 54 | PERSUADE 2.0, grades 6 to 12, about 2010 to 2020 | local only |
| ai | fiction, essay, science | 36 | four local models, nine prompts | `ai/`, committed |
| ai | student essay | 48 | four local models, six PERSUADE assignments, two seeds | local only |
| mixed | fiction, essay, science | 12 | a local model edited one excerpt from each book | `mixed/`, committed |
| mixed | student essay | 12 | a local model edited one essay for each assignment | local only |

The book excerpts come from Project Gutenberg eBooks 1228, 944, 205, 2701, 201
and 308. These works are in the public domain in the United States. The
excerpts are seeded, so `scripts/provenance_human.py` makes the same ones
again. The Project Gutenberg header and footer are not included.

PERSUADE 2.0 is released under CC BY-NC-SA 4.0. Its essays, the AI essays
written to its assignments and the edits of its essays stay on the machine
that ran them. The manifest carries their hashes. For each assignment the
sample holds three essays by writers the school recorded as English learners
and six by the others: 18 learners and 36 others in all.

The models are `qwen2.5:3b`, `qwen2.5:7b`, `qwen3:8b` and `olmo2:7b`, run
through a local Ollama server on 21 October 2026. Each document records the
model digest, the Ollama version, the prompt (or its hash, for a PERSUADE
assignment), the seed and the sampling options. The two edit models are
`qwen2.5:7b` and `olmo2:7b`. Model output is kept as it came back, including
a reply in which the model describes itself as a program and one with a stray non-Latin token.

## Results

Measured on 21 October 2026 over 183 documents. Intervals are Wilson 95% for
rates and percentile bootstrap 95% for AUROC. `results.json` holds every
figure; `scripts/provenance_eval.py` writes it.

Articulate's bench call is "flagged" when the default profile finds a high
or medium pattern or when the cadence check fires.

| Articulate, against ground truth | Value | 95% interval |
|:-|-:|:-|
| Recall on AI text | 84 of 84 (1.00) | 0.96 to 1.00 |
| False-positive rate on human text | 57 of 75 (0.76) | 0.65 to 0.84 |
| Precision | 84 of 141 (0.60) | 0.51 to 0.67 |

By genre, the human false-positive rate is 7 of 9 for fiction, 3 of 3 for
the essay, 6 of 6 for science, 0 of 3 for the speeches and 41 of 54 for
student essays. Among student essays it is 10 of 18 (0.56, 0.34 to 0.75) for
English learners and 31 of 36 (0.86, 0.71 to 0.94) for the others. Recall is
21 of 21 for each of the four models. Mixed documents were flagged 23 of 24
times.

Precision of 0.60 sits close to the share of AI documents in the measured set
(84 of 159, 0.53). On this corpus the bench call separates AI text from human
text only a little better than chance. The human documents that flag mostly
carry intensifiers, contrast pairs, stock transitions and closing lines,
which nineteenth-century prose and school essays use as freely as the models
do. A flag names a pattern in the text. It does not say who wrote it.

| Comparison detector | AUROC | 95% interval |
|:-|-:|:-|
| Binoculars, Qwen3-VL 4B observer and 8B performer | 0.85 | 0.79 to 0.91 |
| Fast-DetectGPT, Qwen3-VL 4B as sampling and scoring model | 0.81 | 0.74 to 0.88 |

Binoculars scores the Qwen models' text as more machine-like than the OLMo
model's text: AUROC 0.96 for `qwen3:8b` against 0.80 for `olmo2:7b`. The three
speeches score as the most machine-like texts in the corpus, from 0.19 to
0.35 against an AI range of 0.64 to 1.25. They are among the most quoted
texts in English, and a model that has memorised them predicts every word.

Agreement between the two calls depends on where Binoculars is cut. At the
score where 10% of the human texts here flag, set on this corpus, the two
agree on 56 of 159 documents (0.35, 0.28 to 0.43). Articulate flags 99
documents Binoculars passes, and Binoculars flags four that Articulate
passes: the three speeches and one student essay.

## Limits

- Time gap. The human books and speeches date from 1776 to 1889 and the
  student essays from about 2010 to 2020. Every AI text dates from 2026. A
  measure that tracks period style can look like a good detector here.
- No recent human text of certain origin. The maintainer's own published
  writing was drafted with AI tools, so it cannot serve as human ground truth.
- No journalism and no forum posts. No public-domain or openly licensed set
  was on hand, and no new download was made for this run.
- No AI draft edited by a person. That class needs a human editor, and none
  took part.
- Small classes. Three essay excerpts and six science excerpts give wide
  intervals.
- Detector family. Both comparison detectors use Qwen models, and three of
  the four generators are Qwen models.
- Binoculars here is a reimplementation with a different model pair from
  the paper, and the paper's thresholds do not apply. Pass two uses the
  observer's top 2,048 probabilities per position; the mass left out
  averages 0.004 and reaches 0.020.

## Reproducing

```
python scripts/provenance_human.py --gutenberg DIR --persuade persuade_corpus_2.0_train.csv
python scripts/provenance_generate.py --model qwen2.5:7b --persuade persuade_corpus_2.0_train.csv
py -3.13 scripts/provenance_detectors.py observer
py -3.13 scripts/provenance_detectors.py performer
python scripts/provenance_eval.py
```

Run each GPU step under the machine's GPU lock. A run adds documents and
records beside the existing ones and never rewrites them. A document whose
text no longer matches its hash is skipped.
