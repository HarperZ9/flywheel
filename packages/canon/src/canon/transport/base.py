"""transport/base.py -- the Transport Protocol, refusal hierarchy, and guard.

Every wire (relay, MCP, HTTP, gRPC, stdio pipe) satisfies the Transport shape
and runs guard_push at the top of push(). guard_push holds a single refusal
matrix across every adapter; helpers stay under 20 lines, the top under 30, so
the whole guard fits under one screen and one review. Every subclass of
TransportError roots at TransportError, single-inheritance throughout; no wire-
adjacent handle error escapes canon un-wrapped.

TransportEnvelope, TransportReceipt, and TransportDescriptor are runtime frozen
dataclasses; not Wave 1 schemas (canon.capsule/v1 and canon.adapter/v1 stay a
Wave 1 concern). Descriptor's post_init enforces the closed-vocabulary invariant
on caps and declared_drops and the caps/declared_drops disjointness invariant.

canon carries no clock and no random; idempotency_key derives from record bytes
under a domain-separated sha256 prefix (see canon.textutil.domain_prefix). Two
sends of the same record produce byte-identical envelope bytes on the wire.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from canon.backends.base import (
    CAP_TEMPORAL,
    flatten_for_drops as _backend_flatten_for_drops,
    temporal_in_use,
)
from canon.schema import Record
from canon.textutil import domain_prefix
from canon.transport.capabilities import (
    CAP_AT_LEAST_ONCE,
    CAP_AT_MOST_ONCE,
    CAP_PROVENANCE_PRESERVING,
    CAP_TEMPORAL_PRESERVING,
    TRANSPORT_CAPABILITIES,
)
from canon.validator import validate_record


class TransportError(Exception):
    """Root of every transport-level refusal."""


class UnsupportedKind(TransportError):
    """Record kind absent from transport.supported_kinds()."""


class DropError(TransportError):
    """Record exercises a record-enforceable cap the transport declared dropped."""


class SchemaMismatch(TransportError):
    """Envelope pin mismatch or a validator problem."""


class ContentTooLarge(TransportError):
    """Canonical envelope bytes exceed the transport's size_limit_bytes."""


class PayloadCorrupt(TransportError):
    """Wire decode failure (json.loads, Record.from_dict, or round-trip)."""


class IdentityMismatch(TransportError):
    """Fetched record's derived key does not match the requested key."""


class DuplicatePush(TransportError):
    """Replay-safe transport observed matching idempotency key, different bytes."""


class Unreachable(TransportError):
    """Handle raised OSError, ConnectionError, or TimeoutError; wrapped."""


class AuthRefused(TransportError):
    """Handle raised a 401/403/OAuth-refused equivalent; wrapped."""


class RateLimited(TransportError):
    """Handle raised a 429 equivalent; carries advisory retry_after."""

    def __init__(self, message: str, *, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class RemoteRefused(TransportError):
    """Handle-side catch-all; carries cause_text the handle reported."""

    def __init__(self, message: str, *, cause_text: str = ""):
        super().__init__(message)
        self.cause_text = cause_text


_PROV_EXTRA_FIELDS = ("native_id", "session_id", "create_ord", "create_time",
                      "model_slug")


def _extra_provenance(record: Record) -> bool:
    return any(getattr(record.provenance, name) is not None
               for name in _PROV_EXTRA_FIELDS)


def capabilities_required(record: Record) -> frozenset[str]:
    """Record-enforceable transport caps this single record exercises. Temporal
    iff temporal in use; provenance iff any nullable provenance field beyond
    harness+source_hash is set. Sized is transport-relative and handled by
    guard_push's size branch."""
    caps: set[str] = set()
    if temporal_in_use(record):
        caps.add(CAP_TEMPORAL_PRESERVING)
    if _extra_provenance(record):
        caps.add(CAP_PROVENANCE_PRESERVING)
    return frozenset(caps)


def idempotency_key(record: Record) -> str:
    """Deterministic sha256 of canonical record bytes under the
    canon-transport/v1 domain prefix. Byte-stable across runs and hosts;
    domain-separated from R2's canon-vault/v1 digest by construction."""
    prefix = domain_prefix("canon-transport")
    return hashlib.sha256(
        (prefix + record.to_json()).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class TransportEnvelope:
    """The wire payload: canonical record JSON plus pin, idempotency key, and
    optional create_ord. to_canonical_json is byte-stable across runs and never
    carries a wall clock, a random field, or a host-path leak."""

    record_json: str
    pin: str
    idempotency_key: str
    create_ord: int | None = None

    def to_canonical_json(self) -> str:
        return json.dumps(
            {"create_ord": self.create_ord,
             "idempotency_key": self.idempotency_key,
             "pin": self.pin,
             "record": self.record_json},
            sort_keys=True,
            separators=(",", ":"),
        )


@dataclass(frozen=True, slots=True)
class TransportReceipt:
    """What push returns. duplicate is True when the transport observed a
    matching prior push (idempotent replay), False on first accept."""

    transport_name: str
    record_key: str
    idempotency_key: str
    accepted: bool
    duplicate: bool = False


@dataclass(frozen=True, slots=True)
class TransportDescriptor:
    """Machine-readable adapter summary. post_init enforces closed-vocabulary on
    caps and declared_drops, disjointness, and the at-most/at-least exclusion."""

    name: str
    pin: str
    caps: frozenset[str]
    declared_drops: frozenset[str]
    size_limit_bytes: int
    notes: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or self.name == "":
            raise ValueError("descriptor name must be a non-empty string")
        bad_caps = frozenset(self.caps) - TRANSPORT_CAPABILITIES
        if bad_caps:
            raise ValueError(f"caps has unknown tokens: {sorted(bad_caps)}")
        bad_drops = frozenset(self.declared_drops) - TRANSPORT_CAPABILITIES
        if bad_drops:
            raise ValueError(
                f"declared_drops has unknown tokens: {sorted(bad_drops)}")
        overlap = frozenset(self.caps) & frozenset(self.declared_drops)
        if overlap:
            raise ValueError(
                f"caps and declared_drops must be disjoint: {sorted(overlap)}")
        if CAP_AT_MOST_ONCE in self.caps and CAP_AT_LEAST_ONCE in self.caps:
            raise ValueError(
                "caps must not include both at-most-once and at-least-once")
        if not isinstance(self.size_limit_bytes, int) or self.size_limit_bytes <= 0:
            raise ValueError("size_limit_bytes must be a positive int")


@runtime_checkable
class Transport(Protocol):
    """The transport seam. An adapter holds records, dispatches them under
    domain-separated idempotency keys, and returns them field-identical but for
    caps it declared dropped."""

    name: str

    def supported_kinds(self) -> frozenset[str]: ...

    def caps(self) -> frozenset[str]: ...

    def declared_drops(self) -> frozenset[str]: ...

    def pin(self) -> str: ...

    def describe(self) -> TransportDescriptor: ...

    def flatten(self, record: Record) -> Record: ...

    def push(self, record: Record) -> TransportReceipt: ...

    def fetch(self, scope: str, id: str) -> Record | None: ...

    def list_keys(self, scope: str) -> list[str]: ...

    def list_all(self) -> list[str]: ...


def _check_kind(transport: Transport, record: Record) -> None:
    if record.kind not in transport.supported_kinds():
        raise UnsupportedKind(
            f"{transport.name} does not carry kind {record.kind!r}; "
            f"supported: {sorted(transport.supported_kinds())}")


def _check_validator(transport: Transport, record: Record) -> None:
    problems = validate_record(record)
    if problems:
        raise SchemaMismatch(f"{transport.name}: {problems[0]}")


def _check_pin(transport: Transport, record: Record) -> None:
    envelope_pin = record.to_dict()["canon_schema"]
    if envelope_pin != transport.pin():
        raise SchemaMismatch(
            f"{transport.name} speaks pin {transport.pin()!r} but record "
            f"carries {envelope_pin!r}")


def _check_drops(transport: Transport, record: Record) -> None:
    blocked = capabilities_required(record) & transport.declared_drops()
    if blocked:
        raise DropError(
            f"{transport.name} drops {sorted(blocked)}; record {record.id!r} "
            f"exercises it -- flatten() first to opt into the loss.")


def _cheap_size(record: Record) -> int:
    total = len(record.id) + len(record.scope) + len(record.kind)
    if isinstance(record.data, dict):
        for key, value in record.data.items():
            total += len(str(key)) + len(str(value))
    return total


def _check_size_cheap(transport: Transport, record: Record) -> None:
    limit = transport.describe().size_limit_bytes
    cheap = _cheap_size(record)
    if cheap > limit:
        raise ContentTooLarge(
            f"{transport.name}: cheap-size {cheap} exceeds limit {limit} "
            f"for record {record.id!r}")


def _check_size_full(transport: Transport, record: Record) -> None:
    limit = transport.describe().size_limit_bytes
    size = len(record.to_json().encode("utf-8"))
    if size > limit:
        raise ContentTooLarge(
            f"{transport.name}: envelope of {size} bytes exceeds limit {limit}")


def guard_push(transport: Transport, record: Record) -> None:
    """The shared pre-dispatch check every Transport runs at the top of push().
    Six branches, cheapest first: unsupported kind, validator, pin mismatch,
    record-enforceable drop, cheap-size heuristic, canonical-size gate."""
    _check_kind(transport, record)
    _check_validator(transport, record)
    _check_pin(transport, record)
    _check_drops(transport, record)
    _check_size_cheap(transport, record)
    _check_size_full(transport, record)


def default_flatten(record: Record, transport_drops: frozenset[str]) -> Record:
    """Map transport-side record-enforceable drops onto the record. Only
    temporal-preserving maps to a removable record-level cap (backends'
    CAP_TEMPORAL). Provenance-preserving is not removable at record level;
    sized-payload-limit cannot be resolved by flatten. Both honest nulls at D-72."""
    to_strip: frozenset[str] = (frozenset({CAP_TEMPORAL})
                                if CAP_TEMPORAL_PRESERVING in transport_drops
                                else frozenset())
    return _backend_flatten_for_drops(record, to_strip)
