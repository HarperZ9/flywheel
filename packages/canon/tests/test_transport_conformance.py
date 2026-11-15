"""Transport conformance suite: every case is parametrized over a
`transport_factory` fixture. FakeTransport wires each knob on FakeRelayHandle
to the refusal branch a real relay could trip; a live relay adapter added later
runs the same suite against its own factory and inherits every guarantee."""
from __future__ import annotations

import pytest

from canon.schema import (
    KIND_EPISODIC_MEMORY,
    Provenance,
    Record,
    SCOPES,
    Temporal,
)
from canon.transport import (
    AuthRefused,
    CAP_TEMPORAL_PRESERVING,
    ContentTooLarge,
    DropError,
    DuplicatePush,
    IdentityMismatch,
    PayloadCorrupt,
    RateLimited,
    SchemaMismatch,
    Transport,
    Unreachable,
    UnsupportedKind,
)

from ._fakes import FakeRelayHandle
from ._fake_transport import FakeTransport


def _block(rid: str = "b", scope: str = "global",
           temporal: Temporal | None = None) -> Record:
    return Record(
        kind="personality-block", id=rid, scope=scope,
        data={"title": "t", "body": "b"},
        provenance=Provenance(harness="author", source_hash="a" * 64),
        temporal=temporal)


@pytest.fixture
def transport_factory():
    """Yield a callable that builds a fresh FakeTransport. A live relay adapter
    added later replaces this fixture; the suite otherwise stays byte-identical."""
    def build(*, handle=None, **kwargs) -> FakeTransport:
        return FakeTransport(handle=handle, **kwargs)
    return build


# --- Protocol conformance ---------------------------------------------------

def test_factory_returns_a_transport(transport_factory) -> None:
    assert isinstance(transport_factory(), Transport)


def test_describe_matches_transport_fields(transport_factory) -> None:
    t = transport_factory()
    desc = t.describe()
    assert desc.name == t.name
    assert desc.pin == t.pin()
    assert desc.caps == t.caps()
    assert desc.declared_drops == t.declared_drops()


# --- Round-trip -------------------------------------------------------------

def test_push_then_fetch_is_field_identical(transport_factory) -> None:
    t = transport_factory()
    rec = _block("a")
    receipt = t.push(rec)
    assert receipt.accepted is True
    fetched = t.fetch(rec.scope, rec.id)
    assert fetched is not None
    assert fetched.to_dict() == rec.to_dict()


def test_fetch_missing_returns_none(transport_factory) -> None:
    t = transport_factory()
    assert t.fetch("global", "does-not-exist") is None


def test_list_keys_returns_scope_prefixed_sorted(transport_factory) -> None:
    t = transport_factory()
    for rid in ("c", "a", "b"):
        t.push(_block(rid, "global"))
    keys = t.list_keys("global")
    assert keys == sorted(keys)
    assert all(k.startswith("global/") for k in keys)


def test_list_all_iterates_every_scope(transport_factory) -> None:
    t = transport_factory()
    t.push(_block("g", "global"))
    t.push(_block("w", "workspace"))
    seen = set(t.list_all())
    assert "global/g" in seen
    assert "workspace/w" in seen
    # list_all touches every scope even when empty.
    empty = transport_factory()
    for scope in SCOPES:
        assert empty.list_keys(scope) == []


# --- Idempotency and duplicate detection ------------------------------------

def test_push_twice_same_record_is_idempotent(transport_factory) -> None:
    t = transport_factory()
    rec = _block("a")
    r1 = t.push(rec)
    r2 = t.push(rec)
    assert r1.idempotency_key == r2.idempotency_key


def test_duplicate_push_tampered_raises_duplicate(transport_factory) -> None:
    handle = FakeRelayHandle(duplicate_push_tampered=True)
    t = transport_factory(handle=handle)
    rec = _block("a")
    t.push(rec)
    with pytest.raises(DuplicatePush):
        t.push(rec)


# --- Wire-side refusals wrapped as TransportError ---------------------------

def test_push_on_unreachable_raises_unreachable(transport_factory) -> None:
    t = transport_factory(handle=FakeRelayHandle(unreachable=True))
    with pytest.raises(Unreachable):
        t.push(_block("a"))


def test_fetch_on_unreachable_raises_unreachable(transport_factory) -> None:
    t = transport_factory(handle=FakeRelayHandle(unreachable=True))
    with pytest.raises(Unreachable):
        t.fetch("global", "a")


def test_list_keys_on_unreachable_raises_unreachable(transport_factory) -> None:
    t = transport_factory(handle=FakeRelayHandle(unreachable=True))
    with pytest.raises(Unreachable):
        t.list_keys("global")


def test_auth_refused_wraps_permissionerror(transport_factory) -> None:
    t = transport_factory(handle=FakeRelayHandle(auth_refused=True))
    with pytest.raises(AuthRefused):
        t.push(_block("a"))


def test_rate_limited_wraps_runtimeerror(transport_factory) -> None:
    t = transport_factory(handle=FakeRelayHandle(rate_limited_every=1))
    with pytest.raises(RateLimited) as exc:
        t.push(_block("a"))
    assert exc.value.retry_after == 0.5


# --- Fetch-side refusals -----------------------------------------------------

def test_corrupt_on_fetch_raises_payload_corrupt(transport_factory) -> None:
    handle = FakeRelayHandle(corrupt_on_fetch=True)
    t = transport_factory(handle=handle)
    t.push(_block("a"))
    with pytest.raises(PayloadCorrupt):
        t.fetch("global", "a")


def test_wrong_pin_on_fetch_raises_schema_mismatch(transport_factory) -> None:
    handle = FakeRelayHandle(wrong_pin_on_fetch="canon.record/v99")
    t = transport_factory(handle=handle)
    t.push(_block("a"))
    with pytest.raises(SchemaMismatch):
        t.fetch("global", "a")


def test_oversize_on_fetch_raises_content_too_large(transport_factory) -> None:
    handle = FakeRelayHandle(oversize_on_fetch=True)
    t = transport_factory(handle=handle, size_limit_bytes=512)
    t.push(_block("a"))
    with pytest.raises(ContentTooLarge):
        t.fetch("global", "a")


def test_spoof_wrong_key_raises_identity_mismatch(transport_factory) -> None:
    handle = FakeRelayHandle(spoof_wrong_key=True)
    t = transport_factory(handle=handle)
    t.push(_block("a"))
    with pytest.raises(IdentityMismatch):
        t.fetch("global", "a")


# --- Guard branches through push -------------------------------------------

def test_push_refuses_kind_not_supported(transport_factory) -> None:
    t = transport_factory(supported_kinds=frozenset({KIND_EPISODIC_MEMORY}))
    with pytest.raises(UnsupportedKind):
        t.push(_block("a"))


def test_push_refuses_temporal_preserving_drop(transport_factory) -> None:
    t = transport_factory(
        declared_drops=frozenset({CAP_TEMPORAL_PRESERVING}))
    rec = _block("a", temporal=Temporal(valid_until=5, supersedes=None))
    with pytest.raises(DropError):
        t.push(rec)


def test_flatten_strips_temporal_when_declared(transport_factory) -> None:
    t = transport_factory(
        declared_drops=frozenset({CAP_TEMPORAL_PRESERVING}))
    rec = _block("a", temporal=Temporal(valid_until=5, supersedes=None))
    flat = t.flatten(rec)
    assert flat.temporal is None
    # After flatten the push succeeds.
    t.push(flat)
