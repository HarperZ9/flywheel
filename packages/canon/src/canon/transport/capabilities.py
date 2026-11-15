"""transport/capabilities.py -- the capability vocabulary.

Every token a Transport advertises via caps() or declares dropped via
declared_drops() is a member of TRANSPORT_CAPABILITIES. Three tokens are
record-enforceable: a single record can trigger the drop by its own fields
(temporal-preserving), by carrying provenance beyond the two required fields
(provenance-preserving), or by exceeding the transport's declared size
(sized-payload-limit). The rest are structural properties of a transport, not
triggerable by a lone record; they are declared but not record-enforced by
guard_push.

Reserved tokens (tombstones, streamable, remote-batch) sit in the vocabulary but
no M4 adapter advertises them; reserving them means a Wave 2 band that adds them
does not have to renumber the vocabulary or edit this module.
"""
from __future__ import annotations

# Record-enforceable: a single record can trigger the drop.
CAP_TEMPORAL_PRESERVING = "temporal-preserving"
CAP_PROVENANCE_PRESERVING = "provenance-preserving"
CAP_SIZED_PAYLOAD_LIMIT = "sized-payload-limit"

# Structural: properties of the transport, not of one record's fields.
CAP_REMOTE_READ = "remote-read"
CAP_REMOTE_WRITE = "remote-write"
CAP_AT_MOST_ONCE = "at-most-once"
CAP_AT_LEAST_ONCE = "at-least-once"
CAP_IDEMPOTENT_PUSH = "idempotent-push"
CAP_ORDERING_PRESERVING = "ordering-preserving"
CAP_REPLAY_SAFE = "replay-safe"
CAP_OFFLINE_SAFE = "offline-safe"
CAP_AUDIT_CHAIN = "audit-chain"
CAP_FOREIGN_ENVELOPE = "foreign-envelope"
CAP_SCHEMA_PIN_VERIFIED = "schema-pin-verified"

# Reserved: no M4 adapter advertises these; Wave 2 or a later band adds them.
CAP_TOMBSTONES = "tombstones"
CAP_STREAMABLE = "streamable"
CAP_REMOTE_BATCH = "remote-batch"

TRANSPORT_CAPABILITIES = frozenset({
    CAP_TEMPORAL_PRESERVING,
    CAP_PROVENANCE_PRESERVING,
    CAP_SIZED_PAYLOAD_LIMIT,
    CAP_REMOTE_READ,
    CAP_REMOTE_WRITE,
    CAP_AT_MOST_ONCE,
    CAP_AT_LEAST_ONCE,
    CAP_IDEMPOTENT_PUSH,
    CAP_ORDERING_PRESERVING,
    CAP_REPLAY_SAFE,
    CAP_OFFLINE_SAFE,
    CAP_AUDIT_CHAIN,
    CAP_FOREIGN_ENVELOPE,
    CAP_SCHEMA_PIN_VERIFIED,
    CAP_TOMBSTONES,
    CAP_STREAMABLE,
    CAP_REMOTE_BATCH,
})

# The three record-enforceable tokens. Guard_push blocks a record that exercises
# a record-enforceable token declared dropped, and never a structural token.
RECORD_ENFORCEABLE_TRANSPORT = frozenset({
    CAP_TEMPORAL_PRESERVING,
    CAP_PROVENANCE_PRESERVING,
    CAP_SIZED_PAYLOAD_LIMIT,
})
