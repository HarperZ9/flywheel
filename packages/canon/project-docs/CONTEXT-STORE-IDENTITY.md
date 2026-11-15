# Context store identity

Canon shared context uses one SQLite database as the memory store. The context
store now persists one logical store id in that same database:

- table: `context_store_meta`
- key: `store_id`
- value shape: `ctxstore_<32 lowercase hex>`
- marker table: `context_store_identity_version`
- marker row: `schema_version = 1` or `schema_version = 2`

Version 1 is the shape canon 0.3.0 writes: put rows with plain digests. The
first purge or salted put raises the marker to 2 in the same transaction
(C1-DECISIONS D-148), and canon 0.3.0 refuses a version 2 database as
"identity invalid" instead of reading its purge rows as tampering. Reading
never raises the marker. This version reads both, and a marker at 1 over rows
that need 2 fails integrity.

The id is created once for a database and returned by `canon.context.health`.
`canon.context.ingest`, `canon.context.query`, `canon.context.get` and
`canon.context.purge` accept an optional `expected_store_id`. When present,
Canon reads the stored id and compares it on the same SQLite connection and
transaction that performs the write or read. A mismatch refuses before
returning query/get records, writing capture records, or purging.

Legacy calls without `expected_store_id` remain compatible. They still use the
same store and may initialize the logical id only when the identity metadata and
version marker are both absent. That is the valid shape for a new or
never-migrated legacy store. Once the marker exists, a missing metadata table,
missing id, malformed id, or malformed marker is treated as an invalid
established identity; Canon fails closed rather than minting a replacement id.
A metadata table without the marker is also invalid, because this change has no
accepted-runtime database to migrate from that intermediate shape.

This id names logical store lineage, not a physical host. A copied SQLite file
retains the same id by design. It detects same-path replacement by a newly
initialized context database when callers replay the old expected id; it does not
claim protection against arbitrary hostile database edits or adversarial
filesystem races beneath SQLite's opened connection semantics. If both identity
tables are removed from an established database by an actor with direct write
access, the file can resemble a never-migrated legacy store; this mechanism is a
transaction-local binding check, not tamper-proof storage.
