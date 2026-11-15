# Pangram reference records

Pangram is no longer the baseline. Since 21 October 2026 the baseline is the
[known-provenance corpus](provenance/README.md), with Binoculars and
Fast-DetectGPT as local comparison detectors. The project holds no Pangram
key and plans no Pangram scans. The records and the rescore script below stay
as an optional tool for anyone who holds a key.

The bench prints a Pangram result beside some corpus files. Pangram is an
outside reference point for the bench. No rule, gate, threshold, editor
setting or accept decision reads these records, and no work here aims to move
a Pangram score.

## What a record holds

`pangram-records.jsonl` holds one JSON object per line. Lines are appended
and never rewritten. A new model version adds records beside the old ones.

| Key | Meaning |
|:-|:-|
| `text` | Path under `corpus/` |
| `text_sha256` | SHA-256 of the file's bytes when it was scored |
| `model` | The version string the API returned, or `unrecorded` |
| `model_requested` | The model name sent with the request |
| `observed` | The date of the scan, UTC |
| `source` | How the result reached this file |
| `prediction_short`, `fraction_ai`, `fraction_ai_assisted`, `fraction_human` | The document result |
| `windows` | Per-segment labels and scores, with the segment text removed |
| `reported` | For older records, the result exactly as first written |

A record applies only while the file's hash still matches. The bench and the
agreement report skip a record whose text has changed. Anyone who claims a
detector result on a text should give these three things: the text's hash,
the model version and the date. Without them the claim cannot be checked.

## Records on file

The two oldest records came from the `.pangram` sidecars written by hand
before 18 September 2026: `ai/flagship-clean.txt` as "AI 100%" and
`human/ptacek-tweets.txt` as "Human 100%". Nobody wrote down the model
version or the scan date. They stay on file, labelled `unrecorded`, and the
sidecars stay unchanged.

## Pangram versions

From Pangram's own pages, read on 21 October 2026:

- Pangram 4, released 29 July 2026. The API takes `"model": "pangram-4"`
  and returns `"version": "4.0"`. Pangram 3.3.2 stayed the API default until
  30 September 2026.
- Pangram 4.1, model card dated 19 October 2026. It adds a
  `class_probabilities` field to each segment with three posterior
  probabilities (Human, AI-Assisted, AI-Generated). Inputs, document-level
  output and training data are unchanged from Pangram 4. The model card does
  not give the API model name for 4.1, so a scan records the version string
  the API returns.

## Rescoring

```
python scripts/pangram_rescore.py estimate
python scripts/pangram_rescore.py score --model <name> --max-usd 2.50
python scripts/pangram_agreement.py
```

`estimate` makes no network call. At USD 0.05 per 100 words, rounded up per
text, the eight sendable texts cost USD 2.30. `score` needs `PANGRAM_API_KEY`
and the `pangram-sdk` package. It sends the text and the model name only.
`ptacek-tweets.txt` is never sent, since no redistribution licence is
recorded for it.

## Known limits

- Eight sendable texts, one of them long. Any interval on this corpus is wide.
- Articulate names prose patterns and emits no probability, so calibration
  against Pangram does not apply. Agreement says how often two different
  measures point the same way here. It shows nothing about who wrote a text.
- Pangram's own pages report a false-positive rate of 0.019% on 62,971
  academic texts for Pangram 4 and list reference sections, PDFs with parsing
  artifacts and text under 50 words as less reliable. The Pangram 4.1 card
  reports no academic figure. Neither covers philosophy as its own domain.
