"""canon.transport -- the Protocol seam any transport adapter satisfies.

M4.1 fixes the shape adapters plug into. Canon imports no engine and holds no
runtime dependency; a live wire (relay, MCP, HTTP, gRPC, stdio pipe) lives in the
relay repo and speaks to canon through the Transport Protocol declared here. The
seam ships one refusal surface (TransportError and its subclasses), one canonical
envelope (TransportEnvelope), one receipt shape (TransportReceipt), one adapter
descriptor (TransportDescriptor), and one guard the caller runs at the top of
push (guard_push). Push_many, fetch_many, streaming, and every batch verb stay
out of M4 and defer to Wave 2 under an explicit CAP_REMOTE_BATCH design.
"""
from __future__ import annotations

from canon.transport.base import (
    AuthRefused,
    ContentTooLarge,
    DropError,
    DuplicatePush,
    IdentityMismatch,
    PayloadCorrupt,
    RateLimited,
    RemoteRefused,
    SchemaMismatch,
    Transport,
    TransportDescriptor,
    TransportEnvelope,
    TransportError,
    TransportReceipt,
    Unreachable,
    UnsupportedKind,
    capabilities_required,
    default_flatten,
    guard_push,
    idempotency_key,
)
from canon.transport.capabilities import (
    CAP_AT_LEAST_ONCE,
    CAP_AT_MOST_ONCE,
    CAP_AUDIT_CHAIN,
    CAP_FOREIGN_ENVELOPE,
    CAP_IDEMPOTENT_PUSH,
    CAP_OFFLINE_SAFE,
    CAP_ORDERING_PRESERVING,
    CAP_PROVENANCE_PRESERVING,
    CAP_REMOTE_BATCH,
    CAP_REMOTE_READ,
    CAP_REMOTE_WRITE,
    CAP_REPLAY_SAFE,
    CAP_SCHEMA_PIN_VERIFIED,
    CAP_SIZED_PAYLOAD_LIMIT,
    CAP_STREAMABLE,
    CAP_TEMPORAL_PRESERVING,
    CAP_TOMBSTONES,
    RECORD_ENFORCEABLE_TRANSPORT,
    TRANSPORT_CAPABILITIES,
)
