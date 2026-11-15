# Agent-Action Proof Packet `reverify`

**Verdict: MATCH** -- verify

- **Scope:** verify
- **Sources:** 1 - **Actions:** 1 - **Flagged/uncertain:** 0

## Trace vs Receipt

| Layer | A raw trace shows | This receipt adds |
| --- | --- | --- |
| Action | tool spans -- what ran | actor, target, and a content-addressed span digest |
| Admission | (nothing) | allow / deny / needs-human, the grant it was checked against, and the reason |
| Side effect | (nothing) | class, idempotency key, compensation / rollback, before -> after digest |
| Verification | (nothing) | a re-derivable MATCH / DRIFT / UNVERIFIABLE verdict |

## Actions

### `fs.write` on `/work/config.json` -- MATCH
- tool `fs` - actor `user:zain` - model `claude-opus-4-8`
- **Admission:** ALLOW (grant `grant-fs-write-work`)
- **Side effect:** write; idempotency `9f2c1a7b4e6d...`; reversible (rollback `backup:/work/config.json@span-write-config`); `000000000000...` -> `9f2c1a7b4e6d...`

## Outputs

- `/work/config.json` -- `9f2c1a7b4e6d...`

## Uncertainty

_none_

_Every verdict is re-derivable: the packet emits a crucible thesis + measurements so an independent checker recomputes MATCH/DRIFT/UNVERIFIABLE from the same evidence._