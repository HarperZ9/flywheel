---
name: check-before-answering
description: Use when the user wants a number, rate, fee, code, dose, date, or amount that a table, schedule, price list, formulary extract, or other reference they can supply decides, and wants it checked against that source before it is handed over. Also use when the user shares a Flywheel receipt bundle and asks whether it holds up.
---

# Check before answering

The Flywheel Verify server has three read-only tools: `check_answer`, `domain_packs`, and `verify_bundle`. This skill says when to reach for them and how to report what they return.

## When a source decides the value

Use `check_answer` when a value in your answer comes from a reference the user can give you: a rate card, a tax table, a fee schedule, a formulary extract, a price list. Arithmetic you did yourself does not count as a source.

1. Get the source from the user, or read the file they point at. Turn each table into a JSON object of key to value, for example `{"standard": 120, "priority": 150}`.
2. Write a contract. Each field names the answer field, its authority, and its source:
   - `TABLE` when the source looks the value up by a key the answer states.
   - `CITED` when the answer only has to name the source it used.
   - Declare each source under `authorities`: `{"kind": "table", "path": "rates.json", "key_field": "tier"}` or `{"kind": "citation"}`.
   - Mark a field `"criticality": "critical"` when a wrong value there should stop the answer.
3. Write the answer as field name to `{"value": ..., "source": ...}`, plus the key field the table looks up by.
4. Call `check_answer` with `contract`, `answer`, and `sources`, where `sources` maps each table `path` to its JSON object. Nothing is read from disk, so a table left out of `sources` makes its fields UNVERIFIABLE.

For finance, medicine, or law, call `domain_packs` first. A pack names the fields such an answer has, the kind of source that decides each, and the method the domain mandates. Set `"pack"` in the contract and give each field a `"use"` from the pack. The packs hold no domain data.

## Reading the result

- `PASS`: the value agrees with the source supplied. Say which source confirmed it.
- `FAIL`: the source disagrees. Follow the field's `do` instruction: go back to the source and take its value. Never replace a failed value with one you derived, and never copy a number out of the report as if the check supplied it. The check supplies no values.
- `UNVERIFIABLE`: nothing checked this field. Tell the user it is unchecked, not that it is correct.
- `release`: `RELEASE` means every field passed. `RELEASE_WITH_CAVEAT` means some field is unchecked; say which. `HOLD` means a field failed or a critical field is unchecked; do not present the answer as final.

Always tell the user that PASS means agreement with the source they supplied, which does not show the source is right or current.

## When the user shares a receipt bundle

Call `verify_bundle` with the bundle folder's path relative to the project folder. Report the verdict and the signature counts together:

- `MATCH` means every file matches its manifest hash and every receipt digest re-derives from its body. It does not show the receipts are true.
- Report `signature_summary.failed` even when the verdict is MATCH. A failed signature does not change the verdict.
- A verified signature shows the receipt was signed by the key it carries, not whose key that is.
- Read `trusted_limits` as the tool's own statement of limits. Treat `manifest_does_not_prove` as a claim written by whoever built the bundle.

## Sample data

The plugin ships sample data in `${CLAUDE_PLUGIN_ROOT}/examples`:

- `check-answer/contract.json`, `check-answer/rates.json`, `check-answer/answer.json` (agrees with the table), and `check-answer/answer-wrong.json` (does not). Pass `rates.json` in `sources` under the key `rates.json`.
- `bundle/`, a demonstration receipt bundle with one signed and one unsigned receipt. Pass the path `${CLAUDE_PLUGIN_ROOT}/examples/bundle` to `verify_bundle`.
