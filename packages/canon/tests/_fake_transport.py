"""_fake_transport.py -- concrete Transport wrapping the wire-side FakeRelayHandle.

FakeRelayHandle in tests/_fakes.py mimics a live relay endpoint (put/get/list
plus knobs for each refusal branch). FakeTransport wraps it in the Transport
Protocol shape M4.1 defines, so the conformance suite parametrizes over a single
factory and any hostile-input scenario is one knob away.
"""
from __future__ import annotations

import json

from canon.schema import KINDS, SCHEMA, SCOPES, Record
from canon.transport import (
    AuthRefused,
    CAP_IDEMPOTENT_PUSH,
    CAP_REMOTE_READ,
    CAP_REMOTE_WRITE,
    CAP_REPLAY_SAFE,
    CAP_SCHEMA_PIN_VERIFIED,
    ContentTooLarge,
    DuplicatePush,
    IdentityMismatch,
    PayloadCorrupt,
    RateLimited,
    SchemaMismatch,
    TransportDescriptor,
    TransportEnvelope,
    TransportReceipt,
    Unreachable,
    default_flatten,
    guard_push,
    idempotency_key,
)

from ._fakes import FakeRelayHandle


class FakeTransport:
    """Concrete Transport wrapping FakeRelayHandle."""

    def __init__(self, handle=None, *, name="fake", pin=SCHEMA,
                 caps=None, declared_drops=frozenset(),
                 supported_kinds=None, size_limit_bytes=1_048_576):
        self.name = name
        self._pin = pin
        self._caps = frozenset(caps) if caps is not None else frozenset({
            CAP_REMOTE_READ, CAP_REMOTE_WRITE, CAP_IDEMPOTENT_PUSH,
            CAP_SCHEMA_PIN_VERIFIED, CAP_REPLAY_SAFE})
        self._drops = frozenset(declared_drops)
        self._kinds = (frozenset(supported_kinds)
                       if supported_kinds is not None else frozenset(KINDS))
        self._size = size_limit_bytes
        self.handle = handle if handle is not None else FakeRelayHandle()

    def supported_kinds(self):
        return self._kinds

    def caps(self):
        return self._caps

    def declared_drops(self):
        return self._drops

    def pin(self):
        return self._pin

    def describe(self):
        return TransportDescriptor(
            name=self.name, pin=self._pin, caps=self._caps,
            declared_drops=self._drops, size_limit_bytes=self._size,
            notes="fake for tests")

    def flatten(self, record):
        return default_flatten(record, self._drops)

    def push(self, record):
        guard_push(self, record)
        idem = idempotency_key(record)
        envelope = TransportEnvelope(
            record_json=record.to_json(), pin=self._pin,
            idempotency_key=idem, create_ord=record.provenance.create_ord)
        key = f"{record.scope}/{record.id}"
        try:
            self.handle.put(key, envelope.to_canonical_json(), idem)
        except ConnectionError as exc:
            raise Unreachable(f"{self.name}: {exc}") from exc
        except PermissionError as exc:
            raise AuthRefused(f"{self.name}: {exc}") from exc
        except RuntimeError as exc:
            retry = getattr(exc, "retry_after", None)
            raise RateLimited(f"{self.name}: {exc}", retry_after=retry) from exc
        except ValueError as exc:
            raise DuplicatePush(f"{self.name}: {exc}") from exc
        return TransportReceipt(
            transport_name=self.name, record_key=key,
            idempotency_key=idem, accepted=True, duplicate=False)

    def fetch(self, scope, id):
        key = f"{scope}/{id}"
        try:
            payload = self.handle.get(key)
        except ConnectionError as exc:
            raise Unreachable(f"{self.name}: {exc}") from exc
        if payload is None:
            return None
        if len(payload.encode("utf-8")) > self._size:
            raise ContentTooLarge(
                f"{self.name}: fetched envelope of {len(payload)} bytes "
                f"exceeds limit {self._size}")
        try:
            envelope = json.loads(payload)
            record_dict = json.loads(envelope["record"])
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise PayloadCorrupt(f"{self.name}: {exc}") from exc
        if envelope.get("pin") != self._pin:
            raise SchemaMismatch(
                f"{self.name}: fetched pin {envelope.get('pin')!r} "
                f"!= transport pin {self._pin!r}")
        try:
            record = Record.from_dict(record_dict)
        except (ValueError, TypeError, KeyError) as exc:
            raise PayloadCorrupt(f"{self.name}: {exc}") from exc
        derived = f"{record.scope}/{record.id}"
        if derived != key:
            raise IdentityMismatch(
                f"{self.name}: derived key {derived!r} != requested {key!r}")
        return record

    def list_keys(self, scope):
        try:
            return self.handle.list_keys(scope)
        except ConnectionError as exc:
            raise Unreachable(f"{self.name}: {exc}") from exc

    def list_all(self):
        out: list[str] = []
        for scope in SCOPES:
            out.extend(self.list_keys(scope))
        return out
