"""The detected fallback, not an injected one: when no OS key store is found
at start, the provider is plaintext and status prints the exact string the
docs quote, `plaintext (unavailable: NO_OS_KEY_STORE)`."""
from harness import trace_enc
from harness.trace_enc import NoProvider
from harness.trace_enc_probe import encryption_status


def test_no_key_store_detected_reads_as_the_documented_status(tmp_path, monkeypatch):
    monkeypatch.setattr(trace_enc, "_detect", lambda: NoProvider())
    monkeypatch.setattr(trace_enc, "_DETECTED", [])
    previous = trace_enc.set_default_provider(None)
    try:
        status = encryption_status(tmp_path / "state")
    finally:
        trace_enc.set_default_provider(previous)
    assert status["provider"] == "none"
    assert status["protection"] == "plaintext (unavailable: NO_OS_KEY_STORE)"
