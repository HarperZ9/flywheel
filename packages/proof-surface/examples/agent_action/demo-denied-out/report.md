# Agent-Action Proof Packet `demo-denied`

**Verdict: DRIFT** -- The agent attempted to write /etc/passwd; the grant only covers /work/config.json.

- **Scope:** Grant limited to fs.write on /work/config.json.
- **Sources:** 1 - **Actions:** 1 - **Flagged/uncertain:** 0

## Trace vs Receipt

| Layer | A raw trace shows | This receipt adds |
| --- | --- | --- |
| Action | tool spans -- what ran | actor, target, and a content-addressed span digest |
| Admission | (nothing) | allow / deny / needs-human, the grant it was checked against, and the reason |
| Side effect | (nothing) | class, idempotency key, compensation / rollback, before -> after digest |
| Verification | (nothing) | a re-derivable MATCH / DRIFT / UNVERIFIABLE verdict |

## Actions

### `fs.write` on `/etc/passwd` -- DRIFT
- tool `fs` - actor `user:zain` - model `claude-opus-4-8`
- **Admission:** DENY (grant `grant-fs-write-work`) -- target '/etc/passwd' is outside the grant scope
- **Side effect:** write; idempotency `dead0000beef...`; irreversible; `111111111111...` -> `dead0000beef...`

## Outputs

- `/etc/passwd` -- `dead0000beef...`

## Uncertainty

_none_

_Every verdict is re-derivable: the packet emits a crucible thesis + measurements so an independent checker recomputes MATCH/DRIFT/UNVERIFIABLE from the same evidence._