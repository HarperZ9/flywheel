# F1 — decisions of record

The decisions that frame the storage seam, continuing the log in
F0-DECISIONS.md and recorded in the same shape the `adr-decision` kind captures.
Each is accepted unless marked otherwise.

## D-7 — Encryption at rest is a declared null with a reversible path
**Status:** accepted (this build, 2026-08-28).
**Context:** A backend writes canonical records to disk (JSON files, a SQLite
file) or into an injected store. Records can hold session text and synthesized
persona material. The question is whether F1 encrypts at rest.
**Decision:** F1 stores plaintext and declares that plainly. No backend claims
encryption it does not perform. The reversible path is a cipher-wrapper backend
that wraps any `MemoryBackend` and encrypts the envelope on `put` and decrypts on
`get`, added when a real deployment needs it. It is not built in F1, and no drop
token stands for it, because encryption is not a lost record field.
**Consequence:** the four F1 backends are honest about being plaintext. Disk
protection is the surrounding filesystem and version control until the wrapper
lands. No half-encryption ships.

## D-8 — Silent flatten is refused; the caller opts into every loss
**Status:** accepted (this build).
**Context:** A record can carry a field a target backend cannot hold, most
concretely a live temporal history on the flywheel store. Two designs: flatten
silently on `put`, or refuse and make the caller strip the field first.
**Decision:** Refuse. `guard_put` raises `DropError` when a record exercises a
record-enforceable capability the backend dropped. The caller must call
`flatten()` first, which returns a copy with the removable capability stripped,
and then `put` the flattened record. The loss is always an explicit, visible act.
**Consequence:** `flatten` and `put` are separate steps for a lossy store; a
round-trip that loses a field can never happen by accident. Structural drops
(audit-chain, relations, arbitrary-kind, foreign-provenance) are not
record-triggerable, so they are declared and documented but do not raise; kind
mismatch raises `UnsupportedKind` on its own track.

## D-9 — External engines are reached through an injected handle
**Status:** accepted (this build; follows D-4 self-contained repo).
**Context:** Two adapters map onto engines living in other repos (mneme,
flywheel), yet canon is self-contained and stdlib-only with no runtime
dependency. Importing either package would break that.
**Decision:** The mneme and flywheel adapters take an injected, duck-typed store
handle in their constructor and import no engine package. Each adapter declares
the slice of the engine surface it uses as a `Protocol`; any object with those
methods satisfies it. The real engine store satisfies it in a deployment; a fake
that mirrors the source surface satisfies it in tests.
**Consequence:** canon carries no import of mneme or flywheel. The adapters are
proved against `tests/_fakes.py`, which mirrors the exact surfaces read from
each engine's source this session (mneme's JSON `source_ids`, its content-hash
collision guard and monotonic ordinal, its `supersede` semantics; flywheel's
`INSERT OR REPLACE` upsert by `eid`). Wiring a real handle in is a later phase
and changes no adapter code.

## D-10 — mneme's temporal boundary is a loud put-time refusal, not a silent drop
**Status:** accepted (this build; folds in the F1 adversarial review).
**Context:** mneme is the temporal home, so `temporal` is not in its
`declared_drops()`. But mneme cannot store everything a canon `temporal` block can
carry. `add_memory` (mneme `store.py:323`) has no `valid_until` parameter, and
`supersede` (`store.py:395`) assigns `valid_until` from mneme's own `_next_ord()`
and returns `None` when the target row is absent or already closed
(`store.py:393`). An earlier MnemeBackend stored a record carrying a caller-set
`valid_until` as current (the value lost, a retired fact resurrected) and no-op'd
a `supersedes` whose target was not present yet. Both losses were silent and both
slipped past `guard_put`, since mneme does not declare `temporal` dropped.
**Decision:** The two losses are made loud at put time. A record carrying a
non-null `valid_until` raises `DropError`; the caller `flatten()`s (strip
`valid_until`, keep `supersedes`) and re-puts current-only. A record whose
`supersedes` names a row that is not present and current raises
`MissingSupersedeTarget`; the superseded record is stored first. Splitting the
`temporal` token into a finer vocabulary was considered and rejected: mneme keeps
the supersession pairing, so it does not drop `temporal`, and these refusals are
backend-native (on their own track, like `UnsupportedKind`), not declared drops.
**Consequence:** mneme never silently downgrades a retired record to current and
never silently discards a supersede. `flatten()` on the mneme backend strips only
`valid_until` (a partial flatten), because that is the one temporal field mneme
cannot hold; `supersedes` is preserved. The ordering refusal is a precondition,
not a dropped field, so `flatten()` does not resolve it.

## D-11 — the mneme fake mirrors INSERT OR REPLACE; the idempotency finding is rejected
**Status:** accepted (this build; honest null on a review finding).
**Context:** The F1 review flagged `FakeMnemeStore.add_memory` for overwriting on
a same-content re-put instead of returning the existing row unchanged, calling the
fake divergent from real mneme.
**Decision:** Rejected after a direct read of mneme `store.py:355-360`: real
`add_memory` is `INSERT OR REPLACE` with a fresh `self._next_ord()` and a column
list that omits `valid_until`/`superseded_by`, so a same-content re-put bumps the
ordinal and clears the temporal columns. The fake already mirrors this. The
finding's "returns the existing row unchanged" premise is not what the engine
does; adopting it would make the fake diverge from mneme, not converge.
**Consequence:** The fake is left as-is, and a characterization test
(`test_same_content_reput_is_accepted`) locks the verified real-engine behavior in
so a future "idempotency" change cannot silently break parity. The adapter still
wraps mneme's content-collision `ValueError` (a genuinely different id with
different content) as a `BackendError`, so a caller catches one refusal type.
