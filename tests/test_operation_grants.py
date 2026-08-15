from dataclasses import replace
from datetime import datetime, timedelta, timezone
import os
import re
import stat
import subprocess

import pytest

from harness.operation_grants import (
    GrantError, GrantRequest, GrantStore, load_or_create_owner_ref,
)
from harness.journey_service import JourneyService
from harness.journey_store import JourneyStore
import harness.operation_grants as operation_grants


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


def test_exact_issue_is_idempotent_for_same_digest_and_denies_mismatch(tmp_path):
    """Approval crash retry must keep one planned ref without widening its request."""
    store = GrantStore(tmp_path, clock=lambda: NOW)
    request = _request()
    ref = "gnt_11111111111111111111111111111111"
    first = store.issue_exact(ref, request, approved=True)
    second = GrantStore(tmp_path, clock=lambda: NOW).issue_exact(
        ref, request, approved=True)
    assert first == second == {"grant_ref": ref, "expires_at": request.expires_at,
                               "consumed": False}
    _assert_code("PERMISSION_DENIED", lambda: store.issue_exact(
        ref, replace(request, nonce="different"), approved=True))
    assert store.consume(ref, request, now=NOW)["consumed"] is True


def test_exact_issue_keeps_random_issue_and_digest_only_record_compatible(tmp_path):
    """Adding planned refs must not alter existing random issue or persist authority."""
    store = GrantStore(tmp_path, clock=lambda: NOW)
    random = store.issue(_request(nonce="random"), approved=True)
    exact = store.issue_exact("gnt_22222222222222222222222222222222",
                              _request(nonce="exact"), approved=True)
    stored = b"".join(path.read_bytes() for path in (tmp_path / "grants").rglob("*.json"))
    assert random["grant_ref"] != exact["grant_ref"]
    assert b"journey.append" not in stored and b"nonce" not in stored


def _storage_receipts(tmp_path, monkeypatch, inspect):
    home, state = tmp_path / "home", tmp_path / "state"
    owner = load_or_create_owner_ref(home)
    store = GrantStore(state, clock=lambda: NOW)
    JourneyService(
        owner_ref=owner, store=JourneyStore(state), grants=store, clock=lambda: NOW,
    )
    receipts = {
        "owner_directory": inspect(home),
        "owner_ref": inspect(home / "owner.ref"),
    }
    real_replace = operation_grants.os.replace

    def inspect_then_replace(source, target):
        receipts["grant_temp"] = inspect(source)
        return real_replace(source, target)

    monkeypatch.setattr(operation_grants.os, "replace", inspect_then_replace)
    request = replace(_request(), owner_ref=owner)
    store.issue(request, approved=True)
    journey_owner = state / "journeys" / "v2" / "owners" / owner
    grant_owner = state / "grants" / owner
    receipts["journey_owner_directory"] = inspect(journey_owner) if journey_owner.exists() else None
    receipts["grant_owner_directory"] = inspect(grant_owner)
    receipts["grant_record"] = inspect(next(grant_owner.glob("*.json")))
    return receipts


def _windows_acl_entries(path):
    result = subprocess.run(
        ["icacls", str(path)], check=True, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    return tuple(line.strip() for line in result.stdout.splitlines() if ":(" in line)


@pytest.mark.skipif(os.name != "nt", reason="Windows DACL semantics")
def test_every_owner_artifact_has_one_protected_owner_only_windows_ace(tmp_path, monkeypatch):
    """Inherited local-user ACLs would expose owner and grant state to other accounts."""
    receipts = _storage_receipts(tmp_path, monkeypatch, _windows_acl_entries)
    assert set(receipts) == {
        "owner_directory", "owner_ref", "journey_owner_directory",
        "grant_owner_directory", "grant_temp", "grant_record",
    }
    for label, entries in receipts.items():
        assert entries is not None, label
        assert len(entries) == 1, (label, entries)
        assert "OWNER RIGHTS:" in entries[0] and "(I)" not in entries[0], (label, entries)
        assert "(F)" in entries[0], (label, entries)
        inheritance = label.endswith("directory")
        assert ("(OI)" in entries[0] and "(CI)" in entries[0]) is inheritance


@pytest.mark.skipif(os.name != "nt", reason="Windows open-file deletion semantics")
def test_owner_acl_failure_is_fixed_and_leaves_no_partial_identity(tmp_path, monkeypatch):
    """Failing ACL setup with an open descriptor must not leave a broad empty owner.ref."""
    real_security = operation_grants._windows_owner_only

    def fail_file(path, *, directory):
        if directory:
            return real_security(path, directory=True)
        raise OSError(r"C:\private\operator\acl")

    monkeypatch.setattr(operation_grants, "_windows_owner_only", fail_file)
    with pytest.raises(PermissionError) as failure:
        load_or_create_owner_ref(tmp_path / "home")
    assert str(failure.value) == "OWNER_STORAGE_UNAVAILABLE"
    assert not (tmp_path / "home" / "owner.ref").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_every_owner_artifact_has_owner_only_posix_mode(tmp_path, monkeypatch):
    """A permissive umask must not make any owner or grant artifact group-readable."""
    receipts = _storage_receipts(
        tmp_path, monkeypatch, lambda path: stat.S_IMODE(path.stat().st_mode),
    )
    assert receipts == {
        "owner_directory": 0o700, "owner_ref": 0o600,
        "journey_owner_directory": 0o700, "grant_owner_directory": 0o700,
        "grant_temp": 0o600, "grant_record": 0o600,
    }
