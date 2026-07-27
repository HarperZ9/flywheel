# Writing-score calibration (2026-07-27)

The writing linter's per-100-word score, measured on this repo's real prose
before any CI gate blocks on it. The spec holds the score REPORT-ONLY because
it is noisy on short texts; this record is the baseline that decision rests
on, and the hard-rule gate turns on only over the files measured clean here.

Method: `check_writing.py --json` over the gate set, before and after the
README fix and the writing_profiles.py comment reword in this same change.
Python files are scored on docstrings and comments only.

| file | profile | words | per100w (gated) | report_per100w | hard |
|---|---|---|---|---|---|
| README.md (before) | readme | 1422 | 1.13 | 0.63 | marketing_adjective |
| README.md (after) | readme | 1422 | 1.05 | 0.63 | none |
| scripts/check_writing.py | flavored* | 229 | 1.31 | 0.00 | none |
| scripts/writing_profiles.py (before) | flavored* | 380 | 1.32 | 0.53 | banned_word |
| scripts/writing_profiles.py (after) | flavored* | 382 | 0.79 | 0.52 | none |
| scripts/writing_lists.py | flavored* | 144 | 2.08 | 1.39 | none |
| scripts/writing_pysource.py | flavored* | 90 | 1.11 | 0.00 | none |
| scripts/writing_readability.py | flavored* | 129 | 2.33 | 0.00 | none |

*Python files fall to the flavored default by path; the register is
operational prose either way.

Does not prove: a clean gate is not a good document, and the per-100-word
score is not calibrated ACROSS document lengths; short files swing wide.
The score stays report-only until this table has enough history to pick a
threshold honestly.
