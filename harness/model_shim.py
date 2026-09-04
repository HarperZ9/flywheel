"""model_shim.py: harness-side server for BuildLang's `Model` capability wire
contract (buildc branch feat/model-capability; contract source: the buildlang
repo's docs/SCIENTIFIC-RECEIPT.md Model paragraph and examples/model_propose.bld
header). Not a vendored copy of that doc -- this module IS the implementation,
so the contract is restated here as the thing this code must hold to.

Wire contract: a client connects over TCP, sends ONE prompt line terminated by
a single \n (the prompt itself never contains a newline -- a conforming client
aborts before sending one), then reads the reply until the server CLOSES the
connection. A conforming server writes ONE completion line and closes. The
client trims exactly one trailing \n (and a \r immediately before it, if any)
from what it read. Consequence: the line protocol has no way to carry an
embedded newline in the completion. Every completion is therefore sanitized to
a single line before it is written (see `_sanitize`) -- \r and \n each become
a space. This is not optional cleanup; an unsanitized multi-line completion
would be truncated or corrupted by every conforming client.

Modes (argparse-level, mutually exclusive, exactly one required -- an unknown
or ambiguous mode combination is refused before a socket is ever opened):
  --echo             deterministic completion "echo: " + prompt. For tests,
                      and for buildc-side offline development against a real
                      socket without a model.
  --ollama MODEL      proxy to an ollama endpoint (default --endpoint
                      http://127.0.0.1:11434); see harness/model_ollama.py,
                      including its UNTESTED-LIVE status.

Fail-closed on ollama errors: a connection failure, a non-2xx status, a
malformed body, or a response missing the "response" field writes NOTHING to
the client. The connection is closed and the failure is logged to stderr
only. The client's read-to-close then yields an empty completion, never a
fabricated one -- a client that cannot tell "the model said nothing" from
"the model said something wrong" is worse than one that gets nothing back.

Serving shape: one connection at a time (the contract has no concurrency
requirement). --port 0 (the default) binds an ephemeral port; the actually
bound port is always printed as the first stdout line, flushed, so a caller
(a test, or buildc's offline harness) can read it back before connecting.
--once serves exactly one connection then exits 0; the default serves until
interrupted. Each connection gets its own socket timeout (--conn-timeout,
default 30s) so a client that connects and never sends its newline cannot
wedge the server open forever.

Model boundary receipts (`--receipt-dir PATH`, v1.1 of the shim contract)
live in harness/model_receipts.py: one sealed
`buildlang-model-boundary-receipt/v0` JSON per connection when the flag is
set, byte-identical wire behavior when it is not.
"""
from __future__ import annotations

import argparse
import os
import socket
import sys

from .model_ollama import (fetch_ollama_daemon_digest, ollama_complete,
                           ollama_request_body_bytes)
from .model_receipts import SHIM_VERSION, emit_receipt, sha256_hex, utc_now_iso

MAX_PROMPT_BYTES = 1024 * 1024  # 1 MiB cap on the incoming prompt line
DEFAULT_OLLAMA_ENDPOINT = "http://127.0.0.1:11434"
DEFAULT_CONN_TIMEOUT = 30.0
DEFAULT_HOST = "127.0.0.1"
RECV_CHUNK = 4096


def _sanitize(text: str) -> str:
    """Collapse a completion to one line. The wire protocol trims exactly one
    trailing \n (and a preceding \r) and nothing else, so any \r or \n left
    inside the completion would be corrupted, not carried -- replace both
    with a space rather than let that happen silently."""
    return text.replace("\r", " ").replace("\n", " ")


def _read_prompt_line(conn: socket.socket, max_bytes: int) -> bytes | None:
    """Read one \n-terminated line, bounded at max_bytes.

    Returns the RAW prompt bytes (trailing \n and a preceding \r stripped,
    still undecoded), or None if the connection hit EOF before a newline
    arrived, or the line exceeded max_bytes before one did. Both are protocol
    violations: the caller must close the connection without writing a reply.
    Raw bytes, not a decoded string: a model boundary receipt's `prompt.sha256`
    is sealed over these exact bytes, BEFORE utf-8 decoding (which is lossy --
    the caller decodes separately with errors="replace" for the completion
    logic, but the receipt witnesses what actually crossed the wire).
    """
    buf = bytearray()
    while True:
        chunk = conn.recv(RECV_CHUNK)
        if not chunk:
            return None  # EOF before a newline arrived
        nl = chunk.find(b"\n")
        if nl != -1:
            buf += chunk[:nl]
            if len(buf) > max_bytes:
                return None  # overlong line
            break
        buf += chunk
        if len(buf) > max_bytes:
            return None  # overlong line
    if buf.endswith(b"\r"):
        buf = buf[:-1]
    return bytes(buf)


def echo_complete(prompt: str) -> str:
    return f"echo: {prompt}"


def handle_connection(conn: socket.socket, *, mode: str, model: str, endpoint: str,
                      timeout: float = DEFAULT_CONN_TIMEOUT,
                      receipt_dir: str | None = None, listen: str = "",
                      shim_version: str = SHIM_VERSION) -> None:
    """Serve exactly one request on an already-accepted connection: read the
    prompt line, compute the completion for `mode`, write it sanitized with
    its trailing \n, and return (the caller closes the socket). Writes
    nothing and returns early on a protocol violation or a fail-closed
    ollama error -- the caller's close is then the entire reply.

    When `receipt_dir` is set, emits one sealed model boundary receipt per
    connection (see `emit_receipt` in model_receipts), covering all three
    outcomes: PROTOCOL_VIOLATION (no prompt), FAILED_CLOSED (a prompt but no
    reply), and COMPLETED. `receipt_dir=None` (the default) skips all receipt
    work (no hashing, no daemon-digest fetch, no file I/O), so the wire
    behavior and cost are byte-identical to before this parameter existed.
    """
    request_received_utc = utc_now_iso()
    nonce = os.urandom(4).hex()

    raw = _read_prompt_line(conn, MAX_PROMPT_BYTES)
    if raw is None:
        print("[model_shim] closing connection: overlong or unterminated prompt line",
              file=sys.stderr)
        if receipt_dir is not None:
            emit_receipt(
                receipt_dir, mode=mode, model=model, endpoint=endpoint, listen=listen,
                shim_version=shim_version, nonce=nonce,
                request_received_utc=request_received_utc, reply_written_utc=None,
                prompt_raw=None, reply_bytes=None, outcome="PROTOCOL_VIOLATION",
            )
        return

    prompt = raw.decode("utf-8", errors="replace")
    request_body_sha256 = None
    if mode == "echo":
        completion = echo_complete(prompt)
    else:
        request_body_sha256 = sha256_hex(ollama_request_body_bytes(model, prompt))
        completion = ollama_complete(prompt, model, endpoint, timeout=timeout)
        if completion is None:
            if receipt_dir is not None:
                daemon_digest = fetch_ollama_daemon_digest(model, endpoint, timeout)
                emit_receipt(
                    receipt_dir, mode=mode, model=model, endpoint=endpoint, listen=listen,
                    shim_version=shim_version, nonce=nonce,
                    request_received_utc=request_received_utc, reply_written_utc=None,
                    prompt_raw=raw, reply_bytes=None, outcome="FAILED_CLOSED",
                    request_body_sha256=request_body_sha256, daemon_digest=daemon_digest,
                )
            return  # fail closed: nothing written, see module docstring

    sanitized_bytes = _sanitize(completion).encode("utf-8")
    conn.sendall(sanitized_bytes + b"\n")
    reply_written_utc = utc_now_iso()

    if receipt_dir is not None:
        daemon_digest = (fetch_ollama_daemon_digest(model, endpoint, timeout)
                         if mode == "ollama" else None)
        emit_receipt(
            receipt_dir, mode=mode, model=model, endpoint=endpoint, listen=listen,
            shim_version=shim_version, nonce=nonce,
            request_received_utc=request_received_utc, reply_written_utc=reply_written_utc,
            prompt_raw=raw, reply_bytes=sanitized_bytes, outcome="COMPLETED",
            request_body_sha256=request_body_sha256, daemon_digest=daemon_digest,
        )


def serve(host: str, port: int, *, mode: str, model: str, endpoint: str,
          once: bool, conn_timeout: float, receipt_dir: str | None = None) -> int:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind((host, port))
        srv.listen(1)
        bound_port = srv.getsockname()[1]
        # First stdout line, flushed: the only way a caller (a test, or
        # buildc's offline harness) learns an ephemeral --port 0 bind.
        print(bound_port, flush=True)
        listen = f"{host}:{bound_port}"
        while True:
            conn, _addr = srv.accept()
            conn.settimeout(conn_timeout)
            try:
                handle_connection(conn, mode=mode, model=model, endpoint=endpoint,
                                  timeout=conn_timeout, receipt_dir=receipt_dir,
                                  listen=listen)
            except socket.timeout:
                print("[model_shim] closing connection: timed out", file=sys.stderr)
            except OSError as e:
                print(f"[model_shim] connection error: {e!r}", file=sys.stderr)
            finally:
                conn.close()
            if once:
                return 0
    finally:
        srv.close()


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Harness-side server for BuildLang's Model capability wire contract.")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--echo", action="store_true",
                       help="deterministic completion: 'echo: ' + prompt")
    mode.add_argument("--ollama", metavar="MODEL", default=None,
                       help="proxy to an ollama /api/generate endpoint (UNTESTED-LIVE)")
    ap.add_argument("--endpoint", default=DEFAULT_OLLAMA_ENDPOINT,
                     help=f"ollama base URL (default {DEFAULT_OLLAMA_ENDPOINT})")
    ap.add_argument("--host", default=DEFAULT_HOST,
                     help=f"listen host (default {DEFAULT_HOST})")
    ap.add_argument("--port", type=int, default=0,
                     help="listen port; 0 = ephemeral (default)")
    ap.add_argument("--once", action="store_true",
                     help="serve exactly one connection then exit 0 "
                          "(default: serve until interrupted)")
    ap.add_argument("--conn-timeout", type=float, default=DEFAULT_CONN_TIMEOUT,
                     help=f"per-connection socket timeout in seconds "
                          f"(default {DEFAULT_CONN_TIMEOUT})")
    ap.add_argument("--receipt-dir", default=None, metavar="PATH",
                     help="write a sealed buildlang-model-boundary-receipt/v0 JSON "
                          "per connection to PATH (default: no receipts, wire "
                          "behavior byte-identical to before this flag existed)")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    mode = "echo" if args.echo else "ollama"
    try:
        return serve(args.host, args.port, mode=mode, model=args.ollama or "",
                    endpoint=args.endpoint, once=args.once,
                    conn_timeout=args.conn_timeout, receipt_dir=args.receipt_dir)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
