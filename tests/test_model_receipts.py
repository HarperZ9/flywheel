"""Falsifier for harness/model_receipts.py -- model boundary receipt
emission behind model_shim's `--receipt-dir` flag (the wire protocol itself
is falsified in tests/test_model_shim.py).

Contract: buildlang's docs/MODEL-RECEIPT.md and
docs/superpowers/specs/2026-07-29-model-boundary-receipts-design.md. The
golden fixture (tests/fixtures/model-receipt-golden.json here, the SAME
bytes as compiler/tests/fixtures/model-receipt-golden.json in buildlang) is
the cross-repo pin: if this file's tests and buildlang's
`golden_fixture_reseals_to_its_pinned_seal` ever disagree, the
cross-language canonicalization contract is broken.

Covers: the golden-fixture seal pin and canonical-bytes reproduction, the
sealed field order, hashed_bytes shape, an end-to-end emission round trip
over a real echo-mode connection, prompt/reply hash correctness against the
exact wire bytes, and the FAILED_CLOSED and PROTOCOL_VIOLATION outcome
shapes.
"""
from __future__ import annotations

import hashlib
import json
import socket
from pathlib import Path
from unittest import mock

import pytest

from harness import model_ollama, model_receipts, model_shim
from model_shim_helpers import (GOLDEN_FIXTURE_PATH, cleanup, read_bound_port,
                                read_to_close, spawn_shim, trim_trailing_newline)

GOLDEN_PINNED_SEAL_HEX = "6bb2a09c47f5eaa2e3208a5eadcd6d57d1faffa74a567e024e920571c3794035"


def _load_golden_bytes() -> bytes:
    return GOLDEN_FIXTURE_PATH.read_bytes()


def _load_golden_receipt() -> dict:
    return json.loads(_load_golden_bytes())


def test_golden_fixture_reseals_to_its_pinned_seal():
    """The Python sealer, applied to the golden fixture's UNSEALED body (seal
    blanked, same as the fixture had before it was sealed), must reproduce
    the golden's exact pinned seal hex. This is the Python half of the
    cross-language pin; compiler/src/model_receipt.rs's
    `golden_fixture_reseals_to_its_pinned_seal` is the Rust half."""
    receipt = _load_golden_receipt()
    assert receipt["seal"]["hex"] == GOLDEN_PINNED_SEAL_HEX

    unsealed = json.loads(_load_golden_bytes())  # fresh copy, key order preserved
    unsealed["seal"]["hex"] = ""
    recomputed = model_receipts.seal_receipt(unsealed)
    assert recomputed == GOLDEN_PINNED_SEAL_HEX
    # seal_receipt mutates in place too
    assert unsealed["seal"]["hex"] == GOLDEN_PINNED_SEAL_HEX


def test_golden_fixture_canonicalization_reproduces_its_exact_bytes():
    """Re-serializing the golden fixture through this module's canonical
    on-disk shape (indent=2, ensure_ascii=False, one trailing newline -- the
    exact shape `emit_receipt` writes) reproduces the fixture file's exact
    bytes, key order included. This proves the fixture committed here is not
    just logically equivalent to buildlang's but was produced by (or is
    indistinguishable from) the same canonicalization this shim emits."""
    raw = _load_golden_bytes()
    receipt = json.loads(raw)  # Python dicts preserve JSON object key order
    reserialized = (json.dumps(receipt, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    assert reserialized == raw


def test_golden_fixture_field_order_matches_schema_and_verifies_shape():
    """Key order in the fixture is the sealed canonical order (design section
    2 / MODEL-RECEIPT.md): schema, source, shim, session, prompt, reply,
    model, seed, outcome, seal. Order is load-bearing for the seal, not just
    cosmetic, so pin it explicitly."""
    receipt = _load_golden_receipt()
    assert list(receipt.keys()) == [
        "schema", "source", "shim", "session", "prompt", "reply",
        "model", "seed", "outcome", "seal",
    ]
    assert receipt["schema"] == model_receipts.MODEL_RECEIPT_SCHEMA
    assert receipt["outcome"] == "COMPLETED"
    assert receipt["model"] == {"name": "echo/v1"}  # echo: ollama-only keys OMITTED
    assert receipt["seed"] == {"status": "NOT_SENT"}


def test_hashed_bytes_is_sha256_and_byte_count_over_raw_bytes():
    data = "café".encode("utf-8")  # multi-byte utf-8, 5 bytes / 4 chars
    result = model_receipts.hashed_bytes(data)
    assert result == {"sha256": hashlib.sha256(data).hexdigest(), "bytes": 5}
    assert result["bytes"] != len("café")


@pytest.fixture
def receipt_echo_server(tmp_path):
    """An --echo --once shim started with --receipt-dir pointed at a fresh
    tmp_path subdirectory the shim itself must create (mkdir(parents=True,
    exist_ok=True) in `emit_receipt`)."""
    receipt_dir = tmp_path / "receipts"
    proc = spawn_shim("--echo", "--once", "--receipt-dir", str(receipt_dir))
    try:
        port = read_bound_port(proc)
        yield port, receipt_dir
    finally:
        cleanup(proc)


def _one_receipt(receipt_dir: Path) -> dict:
    files = list(receipt_dir.iterdir())
    assert len(files) == 1, f"expected exactly one receipt file, found {files}"
    return json.loads(files[0].read_text(encoding="utf-8"))


def test_receipt_emitted_end_to_end_over_real_echo_connection(receipt_echo_server):
    port, receipt_dir = receipt_echo_server
    prompt = "ping"
    sock = socket.create_connection(("127.0.0.1", port), timeout=10)
    try:
        sock.sendall((prompt + "\n").encode("utf-8"))
        sock.shutdown(socket.SHUT_WR)
        raw = read_to_close(sock)
    finally:
        sock.close()
    assert trim_trailing_newline(raw) == "echo: ping"

    receipt = _one_receipt(receipt_dir)
    assert receipt["schema"] == model_receipts.MODEL_RECEIPT_SCHEMA
    assert receipt["source"] == "model:echo:echo/v1"
    assert receipt["shim"] == {"name": "model_shim.py",
                               "version": model_receipts.SHIM_VERSION,
                               "mode": "echo"}
    assert receipt["outcome"] == "COMPLETED"
    assert receipt["model"] == {"name": "echo/v1"}
    assert receipt["seed"] == {"status": "NOT_SENT"}
    assert receipt["session"]["reply_written_utc"] is not None

    # This is the same prompt/reply pair as the golden fixture, so the
    # witnessed hashes must match the pin exactly.
    assert receipt["prompt"] == {
        "sha256": "758d61f26a44448384e5c4468a0dcb7a2abe456067b0f7b505bc28b9411fe931",
        "bytes": 4,
    }
    assert receipt["reply"] == {
        "sha256": "de2406a7ccdb9add6361bdf86cfd31dfaa95806f8d42f91102290ae3abe5afae",
        "bytes": 10,
    }

    # The emitted receipt must reseal to itself: the writer's own seal is
    # internally consistent (a live-emission analogue of the golden pin).
    original_hex = receipt["seal"]["hex"]
    recomputed_hex = model_receipts.seal_receipt(json.loads(json.dumps(receipt)))
    assert recomputed_hex == original_hex


def test_receipt_prompt_and_reply_hashes_match_exact_wire_bytes(receipt_echo_server):
    """Hash correctness against the bytes the design names: prompt.sha256 is
    over the raw prompt-line bytes as received (terminator stripped, before
    utf-8 decode); reply.sha256 is over the sanitized completion bytes
    exactly as written, excluding the protocol-terminator \n."""
    port, receipt_dir = receipt_echo_server
    prompt = "hello café receipts"  # exercises multi-byte utf-8 in the prompt
    prompt_bytes = prompt.encode("utf-8")
    sock = socket.create_connection(("127.0.0.1", port), timeout=10)
    try:
        sock.sendall(prompt_bytes + b"\n")
        sock.shutdown(socket.SHUT_WR)
        raw = read_to_close(sock)
    finally:
        sock.close()
    assert raw.endswith(b"\n")
    wire_reply_bytes = raw[:-1]  # exactly one trailing terminator per the wire contract

    receipt = _one_receipt(receipt_dir)
    assert receipt["prompt"]["sha256"] == hashlib.sha256(prompt_bytes).hexdigest()
    assert receipt["prompt"]["bytes"] == len(prompt_bytes)
    assert receipt["reply"]["sha256"] == hashlib.sha256(wire_reply_bytes).hexdigest()
    assert receipt["reply"]["bytes"] == len(wire_reply_bytes)


def test_protocol_violation_emits_receipt_with_null_prompt_and_reply(tmp_path):
    """An overlong/unterminated prompt line is OUTCOME PROTOCOL_VIOLATION:
    `prompt` is null (nothing was ever legally received) and `reply` is null
    (nothing was ever written)."""
    receipt_dir = tmp_path / "receipts"
    proc = spawn_shim("--echo", "--once", "--receipt-dir", str(receipt_dir))
    try:
        port = read_bound_port(proc)
        sock = socket.create_connection(("127.0.0.1", port), timeout=10)
        try:
            sock.sendall(b"partial prompt, never terminated")
            sock.shutdown(socket.SHUT_WR)
            raw = read_to_close(sock)
        finally:
            sock.close()
        assert raw == b""
        proc.wait(timeout=5)
    finally:
        cleanup(proc)

    receipt = _one_receipt(receipt_dir)
    assert receipt["outcome"] == "PROTOCOL_VIOLATION"
    assert receipt["prompt"] is None
    assert receipt["reply"] is None
    assert receipt["session"]["reply_written_utc"] is None
    # Still a validly sealed artifact even though nothing but a refusal
    # happened -- a refusal is a boundary fact too (design section 2 row 8).
    reloaded = json.loads(json.dumps(receipt))
    original_hex = reloaded["seal"]["hex"]
    assert model_receipts.seal_receipt(reloaded) == original_hex


def test_ollama_failed_closed_emits_receipt_with_null_reply(tmp_path):
    """A fail-closed ollama error (network mocked, no live call -- see the
    module docstring) is outcome FAILED_CLOSED: `prompt` is present (the
    request WAS received), `reply` is null (nothing was ever written)."""
    receipt_dir = tmp_path / "receipts"
    receipt_dir.mkdir()
    import urllib.error

    with mock.patch.object(model_ollama.urllib.request, "urlopen",
                           side_effect=urllib.error.URLError("connection refused")):
        client_sock, server_sock = socket.socketpair()
        try:
            client_sock.sendall(b"prompt\n")
            model_shim.handle_connection(
                server_sock, mode="ollama", model="dummy-model",
                endpoint="http://127.0.0.1:99999", timeout=1.0,
                receipt_dir=str(receipt_dir), listen="127.0.0.1:0")
            server_sock.close()
            raw = read_to_close(client_sock)
        finally:
            client_sock.close()
    assert raw == b""

    receipt = _one_receipt(receipt_dir)
    assert receipt["outcome"] == "FAILED_CLOSED"
    assert receipt["reply"] is None
    assert receipt["prompt"] is not None
    assert receipt["prompt"]["sha256"] == hashlib.sha256(b"prompt").hexdigest()
    assert receipt["model"]["daemon_digest"] == {"status": "UNAVAILABLE"}
