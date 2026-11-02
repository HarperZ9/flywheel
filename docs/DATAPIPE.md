# datapipe: access, structure, clean and diffuse one data source

`harness.datapipe` takes one external data source from download to a shareable export, with a receipt at each stage. Standard library only.

| Stage | Module | What it holds you to |
|---|---|---|
| Access | `access.py` | No bytes come down until the terms are read or the record says `unknown` out loud. Basis `read` needs a saved snapshot of the terms page, its sha256, and a licence quote found verbatim in that snapshot. robots.txt is honoured by RFC 9309 rules. Each download is hashed into `SOURCE.json`, `SOURCE.txt` and `SHA256SUMS`. |
| Structure | `schema.py` | Tables become `datapipe.record/1` rows: value, unit, uncertainty, the printed form, and provenance down to file, hash and cell. `validate` refuses a row with no provenance, an unknown unit, or a value that differs from its printed form. |
| Clean | `clean.py`, `clean_core.py`, `clean_relations.py` | Type, range, unit-factor and offset slips (a kelvin value in a Celsius column), shifted cells, exact and near duplicates, label conflicts, broken identities between columns and stuck runs of one value. Each check returns flags, never deletions. |
| Files and edits | `filecheck.py` | Byte checks on each file, the licence claim against its quote, and a change log in which every edit is a dated row that can be reverted. |
| Diffuse | `diffuse.py` | Only sources with terms read on evidence and redistribution `yes` are exported. Everything else lands in `BLOCKLIST.json` with its reasons. `verify_export` rehashes every exported file against `MANIFEST.json`. |

## Limits

A saved terms snapshot shows what a page said on the date it was read. It does not show that the page's licence covers a given file, or that the publisher had the right to grant it; that judgement stays with the reader. Terms older than the stale limit in `filecheck.py` must be read again before export.

## Tests

```bash
python -m pytest tests/test_datapipe.py tests/test_datapipe_gates.py
```

`test_datapipe.py` holds regressions the first study runs hit. `test_datapipe_gates.py` checks the robots rules, the terms gate against a planted wrong quote and a tampered snapshot, the fetch refusal, the licence-quote agreement, change-log reverts and a tampered export.
