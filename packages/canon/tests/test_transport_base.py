"""Unit tests for transport/base.py: Protocol shape, refusal hierarchy,
capability arithmetic, guard_push, TransportEnvelope, TransportDescriptor.

These pin the seam independently of any concrete transport. FakeTransport lives
next door (tests/_fake_transport.py) and gets exercised in the conformance
suite; here we use it only to feed guard_push a known-shaped adapter."""
from __future__ import annotations

import json

import pytest

from canon.backends import CAP_TEMPORAL, flatten_for_drops
from canon.schema import KIND_EPISODIC_MEMORY, Provenance, Record, SCHEMA, Temporal
from canon.textutil import domain_prefix
from canon.transport import (
    AuthRefused,
    CAP_AT_LEAST_ONCE,
    CAP_AT_MOST_ONCE,
    CAP_IDEMPOTENT_PUSH,
    CAP_PROVENANCE_PRESERVING,
    CAP_REMOTE_READ,
    CAP_REMOTE_WRITE,
    CAP_REPLAY_SAFE,
    CAP_SCHEMA_PIN_VERIFIED,
    CAP_TEMPORAL_PRESERVING,
    ContentTooLarge,
    DropError,
    DuplicatePush,
    IdentityMismatch,
    PayloadCorrupt,
    RECORD_ENFORCEABLE_TRANSPORT,
    RateLimited,
    RemoteRefused,
    SchemaMismatch,
    TRANSPORT_CAPABILITIES,
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

from ._fake_transport import FakeTransport


def _block(rid: str = "b", scope: str = "global",
           *, temporal: Temporal | None = None,
           extra_provenance: dict | None = None) -> Record:
    prov = Provenance(harness="author", source_hash="a" * 64,
                      **(extra_provenance or {}))
    return Record(
        kind="personality-block", id=rid, scope=scope,
        data={"title": "t", "body": "b"},
        provenance=prov, temporal=temporal)


# --- Protocol shape and refusal hierarchy -----------------------------------

def test_transport_is_runtime_checkable_protocol() -> None:
    assert isinstance(FakeTransport(), Transport)


def test_all_transport_errors_root_at_transporterror() -> None:
    subclasses = [
        UnsupportedKind, DropError, SchemaMismatch, ContentTooLarge,
        PayloadCorrupt, IdentityMismatch, DuplicatePush, Unreachable,
        AuthRefused, RateLimited, RemoteRefused]
    for cls in subclasses:
        assert issubclass(cls, TransportError), f"{cls} does not root at TransportError"


def test_rate_limited_carries_retry_after() -> None:
    err = RateLimited("throttled", retry_after=0.5)
    assert err.retry_after == 0.5
    assert isinstance(err, TransportError)


def test_remote_refused_carries_cause_text() -> None:
    err = RemoteRefused("server said no", cause_text="upstream 5xx")
    assert err.cause_text == "upstream 5xx"


# --- capabilities_required + idempotency_key --------------------------------

def test_capabilities_required_empty_on_bare_record() -> None:
    assert capabilities_required(_block()) == frozenset()


def test_capabilities_required_temporal_when_in_use() -> None:
    rec = _block(temporal=Temporal(valid_until=5, supersedes=None))
    assert capabilities_required(rec) == frozenset({CAP_TEMPORAL_PRESERVING})


def test_capabilities_required_provenance_on_any_extra_field() -> None:
    for extra in ({"native_id": "n"}, {"session_id": "s"},
                  {"create_ord": 1}, {"create_time": "2026-01-01"},
                  {"model_slug": "m"}):
        rec = _block(extra_provenance=extra)
        assert CAP_PROVENANCE_PRESERVING in capabilities_required(rec), extra


def test_idempotency_key_domain_separated_from_vault() -> None:
    rec = _block()
    transport_key = idempotency_key(rec)
    vault_prefix = domain_prefix("canon-vault")
    assert not transport_key.startswith(vault_prefix)
    assert domain_prefix("canon-transport") != vault_prefix


def test_idempotency_key_deterministic() -> None:
    rec = _block()
    assert idempotency_key(rec) == idempotency_key(rec)


def test_idempotency_key_changes_with_record_bytes() -> None:
    a = idempotency_key(_block("a"))
    b = idempotency_key(_block("b"))
    assert a != b


# --- TransportEnvelope ------------------------------------------------------

def test_envelope_canonical_json_is_byte_stable() -> None:
    env = TransportEnvelope(
        record_json='{"a":1}', pin=SCHEMA,
        idempotency_key="deadbeef", create_ord=7)
    a = env.to_canonical_json()
    b = env.to_canonical_json()
    assert a == b
    parsed = json.loads(a)
    assert list(parsed.keys()) == sorted(parsed.keys())


def test_envelope_carries_no_wall_clock_key() -> None:
    env = TransportEnvelope(
        record_json="{}", pin=SCHEMA, idempotency_key="x", create_ord=None)
    parsed = json.loads(env.to_canonical_json())
    for banned in ("time", "timestamp", "wall_time", "now"):
        assert banned not in parsed


# --- TransportDescriptor invariants -----------------------------------------

def _desc(**over) -> TransportDescriptor:
    base = dict(
        name="t", pin=SCHEMA, caps=frozenset({CAP_REMOTE_WRITE}),
        declared_drops=frozenset(), size_limit_bytes=1024)
    base.update(over)
    return TransportDescriptor(**base)


def test_descriptor_rejects_empty_name() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        _desc(name="")


def test_descriptor_rejects_unknown_cap() -> None:
    with pytest.raises(ValueError, match="unknown tokens"):
        _desc(caps=frozenset({"not-a-real-cap"}))


def test_descriptor_rejects_unknown_drop() -> None:
    with pytest.raises(ValueError, match="unknown tokens"):
        _desc(declared_drops=frozenset({"not-a-real-cap"}))


def test_descriptor_rejects_caps_drops_overlap() -> None:
    with pytest.raises(ValueError, match="disjoint"):
        _desc(caps=frozenset({CAP_TEMPORAL_PRESERVING}),
              declared_drops=frozenset({CAP_TEMPORAL_PRESERVING}))


def test_descriptor_rejects_at_most_and_at_least_together() -> None:
    with pytest.raises(ValueError, match="at-most-once and at-least-once"):
        _desc(caps=frozenset({CAP_AT_MOST_ONCE, CAP_AT_LEAST_ONCE}))


def test_descriptor_rejects_nonpositive_size() -> None:
    with pytest.raises(ValueError, match="size_limit_bytes"):
        _desc(size_limit_bytes=0)
    with pytest.raises(ValueError, match="size_limit_bytes"):
        _desc(size_limit_bytes=-1)


def test_record_enforceable_is_disjoint_subset_of_vocabulary() -> None:
    assert RECORD_ENFORCEABLE_TRANSPORT <= TRANSPORT_CAPABILITIES
    assert len(RECORD_ENFORCEABLE_TRANSPORT) == 3


# --- guard_push branches ----------------------------------------------------

def test_guard_push_refuses_unsupported_kind() -> None:
    transport = FakeTransport(supported_kinds=frozenset({KIND_EPISODIC_MEMORY}))
    with pytest.raises(UnsupportedKind):
        guard_push(transport, _block())


def test_guard_push_refuses_validator_failure() -> None:
    bad = Record(
        kind="personality-block", id="b", scope="global",
        data={"body": "b"},  # missing required 'title'
        provenance=Provenance(harness="author", source_hash="a" * 64))
    transport = FakeTransport()
    with pytest.raises(SchemaMismatch):
        guard_push(transport, bad)


def test_guard_push_refuses_pin_mismatch() -> None:
    transport = FakeTransport(pin="canon.record/v99")
    with pytest.raises(SchemaMismatch, match="pin"):
        guard_push(transport, _block())


def test_guard_push_refuses_temporal_preserving_drop() -> None:
    transport = FakeTransport(declared_drops=frozenset({CAP_TEMPORAL_PRESERVING}))
    rec = _block(temporal=Temporal(valid_until=5, supersedes=None))
    with pytest.raises(DropError, match="temporal-preserving"):
        guard_push(transport, rec)


def test_guard_push_refuses_provenance_preserving_drop() -> None:
    transport = FakeTransport(
        declared_drops=frozenset({CAP_PROVENANCE_PRESERVING}))
    rec = _block(extra_provenance={"native_id": "abc"})
    with pytest.raises(DropError, match="provenance-preserving"):
        guard_push(transport, rec)


def test_guard_push_refuses_via_cheap_size_branch() -> None:
    # cheap-size counts id+scope+kind+data keys+values; make sum > limit
    long_body = "X" * 200
    rec = Record(
        kind="personality-block", id="b", scope="global",
        data={"title": "t", "body": long_body},
        provenance=Provenance(harness="author", source_hash="a" * 64))
    transport = FakeTransport(size_limit_bytes=64)
    with pytest.raises(ContentTooLarge, match="cheap-size"):
        guard_push(transport, rec)


def test_guard_push_refuses_via_full_size_branch() -> None:
    # cheap-size passes (small strings), full canonical json exceeds limit.
    rec = _block()
    canonical = len(rec.to_json().encode("utf-8"))
    transport = FakeTransport(size_limit_bytes=canonical - 1)
    with pytest.raises(ContentTooLarge, match="envelope"):
        guard_push(transport, rec)


# --- default_flatten -------------------------------------------------------

def test_default_flatten_strips_temporal_on_declared_drop() -> None:
    rec = _block(temporal=Temporal(valid_until=5, supersedes=None))
    out = default_flatten(rec, frozenset({CAP_TEMPORAL_PRESERVING}))
    assert out.temporal is None


def test_default_flatten_identity_when_no_drops() -> None:
    rec = _block(temporal=Temporal(valid_until=5, supersedes=None))
    out = default_flatten(rec, frozenset())
    assert out.temporal == rec.temporal


def test_default_flatten_does_not_mutate_source() -> None:
    rec = _block(temporal=Temporal(valid_until=5, supersedes=None))
    _ = default_flatten(rec, frozenset({CAP_TEMPORAL_PRESERVING}))
    assert rec.temporal is not None


def test_default_flatten_matches_backend_flatten_for_temporal() -> None:
    rec = _block(temporal=Temporal(valid_until=5, supersedes=None))
    a = default_flatten(rec, frozenset({CAP_TEMPORAL_PRESERVING}))
    b = flatten_for_drops(rec, frozenset({CAP_TEMPORAL}))
    assert a.to_dict() == b.to_dict()


# --- TransportReceipt shape -------------------------------------------------

def test_receipt_shape_frozen_and_defaults_duplicate_false() -> None:
    receipt = TransportReceipt(
        transport_name="t", record_key="global/b",
        idempotency_key="k", accepted=True)
    assert receipt.duplicate is False
    with pytest.raises((AttributeError, Exception)):
        receipt.accepted = False  # frozen
