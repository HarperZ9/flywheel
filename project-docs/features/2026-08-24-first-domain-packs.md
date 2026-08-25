# The first three domain packs: medicine, finance, design

Date: 2026-08-24

## The claim this closes

The extension charter line reads: prove any domain plugs in without
code changes. Until today that was a mechanism (`domain_pack.py`, the
`/api/journeys/extensions/domain-pack-project` route) with zero
first-party packs riding it. Now three ride it, all as repo data.

## What shipped

`packs/medicine-terminology`, `packs/finance-compliance`,
`packs/design-tokens` -- each a `flywheel.domain-pack/v1` manifest plus
fixtures, capabilities `["data"]` only:

1. **Medicine terminology**: preferred-term and known-misspelling sets.
2. **Finance claims screening**: prohibited-phrase set and the
   figures-carry-denominators rule.
3. **Design tokens**: contrast thresholds and the two-typeface rule.

Every pack binds deterministic oracles whose `source_sha256` equals the
sha256 of the fixture file it names, so a stale binding is detectable,
and every pack carries limitations and a does_not_prove list: a passed
terminology screen is not clinical correctness; a passed claims screen
is not regulatory compliance; a passed token check is not good design.

## Verification

```text
python -m pytest tests/test_first_domain_packs.py -q         # 6/6
python -m pytest tests/ -q                                   # exit 0
python scripts/check_file_gate.py                            # clean
python scripts/check_verifier_stdlib.py                      # clean
python scripts/check_claim_language.py                       # clean
```

## Does not prove

The packs are admitted checklists, not certified domain authority: QA
passing says each pack refuses its own planted false accepts, nothing
stronger. Admission through the gateway route remains grant-gated and
the server-side contract registry stays empty until the operator
accepts contracts; these packs are repo data a deployment can admit,
not yet admitted runtime state.
