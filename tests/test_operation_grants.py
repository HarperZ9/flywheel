from dataclasses import replace
from datetime import datetime, timedelta, timezone
import os
import re
import stat

import pytest

from harness.operation_grants import (
    GrantError, GrantRequest, GrantStore, load_or_create_owner_ref,
)


NOW = "2026-08-14T12:00:00Z"
OWNER = "owner_0123456789abcdef0123456789abcdef"
JOURNEY = "jrn_0123456789abcdef0123456789abcdef"
HEAD = "a" * 64


def _request(**changes):
    values = {
        "owner_ref": OWNER, "journey_ref": JOURNEY,
        "expected_event_head": HEAD, "operation_sha256": "b" * 64,
        "tool": "journey.append", "arguments_sha256": "c" * 64,
        "scopes": ("journey:append",), "data_refs": ("evidence/input.json",),
        "expires_at": "2026-08-14T12:02:00Z", "nonce": "nonce-0123456789",
    }
    values.update(changes)
    return GrantRequest(**values)


def _assert_code(expected, call):
    with pytest.raises(GrantError) as failure:
        call()
    assert failure.value.code == str(failure.value) == expected


def test_owner_ref_is_stable_across_bearer_rotation_and_owner_readable_only(tmp_path):
    """Deriving identity from a bearer token or rewriting it would lose owner custody."""
    first_token, second_token = "first-rotatable-token", "second-rotatable-token"
    first = load_or_create_owner_ref(tmp_path)
    second = load_or_create_owner_ref(tmp_path)

    assert first == second
    assert re.fullmatch(r"owner_[0-9a-f]{32}", first)
    stored = (tmp_path / "owner.ref").read_bytes()
    assert first_token.encode() not in stored and second_token.encode() not in stored
    if os.name != "nt":
        mode = (tmp_path / "owner.ref").stat().st_mode
        assert not (mode & stat.S_IRGRP) and not (mode & stat.S_IROTH)


def test_issue_uses_server_time_for_default_and_rejects_more_than_300_seconds(tmp_path):
    """Trusting a caller TTL would permit a stale approval to outlive the maximum."""
    store = GrantStore(tmp_path, clock=lambda: NOW)
    default = _request(expires_at=None)
    issued = store.issue(default, approved=True)

    assert issued["expires_at"] == "2026-08-14T12:02:00Z"
    effective = replace(default, expires_at=issued["expires_at"])
    assert store.consume(issued["grant_ref"], effective, now=NOW)["consumed"] is True

    too_long = _request(expires_at="2026-08-14T12:05:01Z", nonce="too-long")
    _assert_code("PERMISSION_DENIED", lambda: store.issue(too_long, approved=True))


@pytest.mark.parametrize("field,value", (
    ("journey_ref", "jrn_fedcba9876543210fedcba9876543210"),
    ("expected_event_head", "d" * 64),
    ("operation_sha256", "e" * 64),
    ("tool", "journey.check"),
    ("arguments_sha256", "f" * 64),
    ("scopes", ("journey:append", "network")),
    ("data_refs", ("evidence/other.json",)),
    ("expires_at", "2026-08-14T12:01:59Z"),
    ("nonce", "different-nonce"),
))
def test_grant_rejects_every_non_owner_binding_difference(tmp_path, field, value):
    """Ignoring one bound field would widen a one-operation approval."""
    store = GrantStore(tmp_path, clock=lambda: NOW)
    request = _request()
    issued = store.issue(request, approved=True)

    _assert_code(
        "PERMISSION_DENIED",
        lambda: store.consume(issued["grant_ref"], replace(request, **{field: value}), now=NOW),
    )
    assert store.consume(issued["grant_ref"], request, now=NOW)["consumed"] is True


def test_wrong_owner_cannot_discover_an_existing_grant(tmp_path):
    """Looking outside the authenticated owner directory would enumerate approvals."""
    store = GrantStore(tmp_path, clock=lambda: NOW)
    request = _request()
    issued = store.issue(request, approved=True)
    other = replace(request, owner_ref="owner_fedcba9876543210fedcba9876543210")

    _assert_code(
        "PERMISSION_REQUIRED",
        lambda: store.consume(issued["grant_ref"], other, now=NOW),
    )


def test_denied_expired_and_reused_grants_have_fixed_non_echo_failures(tmp_path):
    """Echoing approval inputs or accepting a second use would disclose or widen authority."""
    store = GrantStore(tmp_path, clock=lambda: NOW)
    request = _request()
    _assert_code("PERMISSION_DENIED", lambda: store.issue(request, approved=False))
    _assert_code("PERMISSION_REQUIRED", lambda: store.consume("gnt_missing", request, now=NOW))

    issued = store.issue(request, approved=True)
    _assert_code(
        "APPROVAL_EXPIRED",
        lambda: store.consume(issued["grant_ref"], request, now="2026-08-14T12:02:00Z"),
    )
    fresh = store.issue(replace(request, nonce="fresh"), approved=True)
    fresh_request = replace(request, nonce="fresh")
    store.consume(fresh["grant_ref"], fresh_request, now=NOW)
    _assert_code(
        "APPROVAL_EXPIRED",
        lambda: GrantStore(tmp_path, clock=lambda: NOW).consume(
            fresh["grant_ref"], fresh_request, now=NOW,
        ),
    )


def test_grant_files_persist_only_digests_expiry_and_consumption_state(tmp_path):
    """Persisting raw approval context would retain private refs or authorization material."""
    request = _request(
        scopes=("credential:opaque-handle",),
        data_refs=(r"C:\private\operator\secret.txt", "token=never-store-me"),
        nonce="private-nonce-never-store",
    )
    store = GrantStore(tmp_path, clock=lambda: NOW)
    issued = store.issue(request, approved=True)
    store.consume(issued["grant_ref"], request, now=NOW)
    stored = b"".join(path.read_bytes() for path in (tmp_path / "grants").rglob("*.*"))

    for forbidden in (b"journey.append", b"private", b"secret", b"token=", b"private-nonce"):
        assert forbidden not in stored
    assert b'"request_sha256"' in stored and b'"consumed":true' in stored


def test_default_ttl_is_exactly_120_seconds(tmp_path):
    """Changing the default lifetime would make grant expiry behavior ambiguous."""
    now = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)
    store = GrantStore(tmp_path, clock=lambda: now.isoformat().replace("+00:00", "Z"))
    issued = store.issue(_request(expires_at=None), approved=True)
    expiry = datetime.fromisoformat(issued["expires_at"].replace("Z", "+00:00"))
    assert expiry - now == timedelta(seconds=120)
