import sys
import tempfile
import time
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from env_authority import (
    AuthorityGrant,
    SCHEMA,
    cached_authority,
    invalidate_cache,
    resolve_authority,
    _grant_cache,
)
from authority_gate import (
    GateResult,
    _audit_enabled,
    check_entitlement,
)
from authority_audit import (
    AuditEntry,
    audit_summary,
    read_audit_log,
    record_gate_check,
)


def _make_grant(status="authorized", seal="pass", entitlements=None,
                surface="claude_code", ttl=3600):
    now = time.time()
    return AuthorityGrant(
        schema=SCHEMA, status=status,
        operator_fingerprint="test_op", machine_fingerprint="test_mach",
        capsule_sha256="test_cap", seal_status=seal,
        surface=surface, entitlements=entitlements or ["transform", "infer"],
        issued_at=now, expires_at=now + ttl if status == "authorized" else 0,
    )


# --- Audit log ---

def test_audit_record_and_read():
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "audit.jsonl"
        record_gate_check(
            gate="test", entitlement="transform", allowed=True,
            reason="authorized", operator_fingerprint="op1",
            machine_fingerprint="mach1", surface="claude_code",
            capsule_sha256="abc123", log_path=log,
        )
        record_gate_check(
            gate="test", entitlement="infer", allowed=False,
            reason="denied", operator_fingerprint="op1",
            log_path=log,
        )
        entries = read_audit_log(log_path=log)
        assert len(entries) == 2
        assert entries[0]["allowed"] is True
        assert entries[1]["allowed"] is False


def test_audit_filter_by_gate():
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "audit.jsonl"
        record_gate_check(gate="launch", entitlement="transform",
                          allowed=True, reason="ok", log_path=log)
        record_gate_check(gate="infer", entitlement="infer",
                          allowed=False, reason="denied", log_path=log)
        entries = read_audit_log(log_path=log, gate="infer")
        assert len(entries) == 1
        assert entries[0]["gate"] == "infer"


def test_audit_filter_by_allowed():
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "audit.jsonl"
        record_gate_check(gate="a", entitlement="x", allowed=True,
                          reason="ok", log_path=log)
        record_gate_check(gate="b", entitlement="y", allowed=False,
                          reason="no", log_path=log)
        denied = read_audit_log(log_path=log, allowed=False)
        assert len(denied) == 1
        assert denied[0]["gate"] == "b"


def test_audit_summary_counts():
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "audit.jsonl"
        for _ in range(3):
            record_gate_check(gate="g", entitlement="e", allowed=True,
                              reason="ok", log_path=log)
        record_gate_check(gate="g", entitlement="e", allowed=False,
                          reason="no", log_path=log)
        s = audit_summary(log_path=log)
        assert s["total"] == 4
        assert s["allowed"] == 3
        assert s["denied"] == 1
        assert s["denial_rate"] == 0.25


def test_audit_empty_log():
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "nonexistent.jsonl"
        entries = read_audit_log(log_path=log)
        assert entries == []
        s = audit_summary(log_path=log)
        assert s["total"] == 0


def test_audit_entry_truncates_capsule():
    entry = AuditEntry(
        timestamp=time.time(), gate="g", entitlement="e",
        allowed=True, reason="ok", operator_fingerprint="op",
        machine_fingerprint="mach", surface="s",
        capsule_sha256="abcdef1234567890abcdef1234567890",
    )
    d = entry.to_dict()
    assert d["capsule_sha256"] == "abcdef123456..."


# --- Grant caching ---

def test_cache_returns_same_grant():
    invalidate_cache()
    g1 = cached_authority(surface="generic_cli")
    g2 = cached_authority(surface="generic_cli")
    if g1.valid:
        assert g1 is g2


def test_invalidate_clears_cache():
    invalidate_cache()
    _grant_cache["test_surface"] = _make_grant(surface="test_surface")
    assert "test_surface" in _grant_cache
    invalidate_cache("test_surface")
    assert "test_surface" not in _grant_cache


def test_invalidate_all():
    invalidate_cache()
    _grant_cache["a"] = _make_grant()
    _grant_cache["b"] = _make_grant()
    invalidate_cache()
    assert len(_grant_cache) == 0


# --- Gated inference ---

def test_inference_loop_gate_blocks():
    from inference_loop import InferenceLoop

    def send_fn(system, messages):
        return "Should not be called"

    loop = InferenceLoop(send_fn, enforce_auth=True)
    grant = _make_grant(status="unauthorized")

    import authority_gate
    original = authority_gate._audit_enabled
    authority_gate._audit_enabled = False
    try:
        from unittest.mock import patch
        with patch("inference_loop._gate_infer") as mock_gate:
            mock_gate.return_value = GateResult(
                allowed=False, gate="infer", entitlement="infer",
                reason="unauthorized: no_capsule",
                checked_at=time.time(),
            )
            result = loop.run("test input", [])
            assert result.succeeded is False
            assert "gate:infer denied" in result.response
            assert len(result.attempts) == 0
    finally:
        authority_gate._audit_enabled = original


def test_inference_loop_gate_allows():
    from inference_loop import InferenceLoop

    responses = ["The answer is 42."]
    idx = [0]

    def send_fn(system, messages):
        i = min(idx[0], len(responses) - 1)
        idx[0] += 1
        return responses[i]

    loop = InferenceLoop(send_fn, enforce_auth=True)

    import authority_gate
    original = authority_gate._audit_enabled
    authority_gate._audit_enabled = False
    try:
        from unittest.mock import patch
        with patch("inference_loop._gate_infer") as mock_gate:
            mock_gate.return_value = GateResult(
                allowed=True, gate="infer", entitlement="infer",
                reason="authorized", checked_at=time.time(),
            )
            result = loop.run("What is the answer?", [])
            assert result.succeeded is True
    finally:
        authority_gate._audit_enabled = original


# --- CLI commands ---

def test_audit_cli_summary():
    from bt_cli import main as bt_main
    old_stdout = sys.stdout
    sys.stdout = StringIO()
    try:
        bt_main(["audit"])
    finally:
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout
    assert "Total:" in output or "No audit" in output.lower() or "total" in output.lower()


def test_audit_cli_recent():
    from bt_cli import main as bt_main
    old_stdout = sys.stdout
    sys.stdout = StringIO()
    try:
        bt_main(["audit", "--recent"])
    finally:
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout
    assert isinstance(output, str)
