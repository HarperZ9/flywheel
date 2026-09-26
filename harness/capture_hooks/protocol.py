"""The capture channel's proof and signature, shared by hook and gateway (7.1).

Two keys come from the gateway token and never the token itself:
`K_s = HMAC(token, "flywheel.capture.server.v1")` proves the listener knows the
token, and `K_c = HMAC(token, "flywheel.capture.client.v1")` signs each request.
The proof is bound to the address and port the gateway bound, so a squatter
that relays a hello to a real gateway on another port gets a proof the hook
rejects. The signature binds method, path, body digest, time, a client nonce,
the server nonce and the address, so a captured request cannot be replayed or
moved. Standard library only: the hook imports this module.
"""
from __future__ import annotations

import hashlib
import hmac
import re

SERVER_LABEL = b"flywheel.capture.server.v1"
CLIENT_LABEL = b"flywheel.capture.client.v1"
HELLO_PATH = "/api/traces/capture/hello"
PING_PATH = "/api/traces/capture/ping"
PROMPT_PATH = "/api/traces/capture/prompt"
STOP_PATH = "/api/traces/capture/stop"
FREEZE_PATH = "/api/traces/capture/freeze"
_COMMIT_TAGS = {"prompt": b"flywheel.turn.prompt.v1", "answer": b"flywheel.turn.answer.v1",
                "freeze": b"flywheel.turn.freeze.v1"}
PREFIX = "/api/traces/capture/"
LOOPBACK = ("127.0.0.1", "::1")
SCHEME = "FW-Sig"
_HEX16 = re.compile(r"[0-9a-f]{32}\Z")
_HEX32 = re.compile(r"[0-9a-f]{64}\Z")
_FIELD = re.compile(r"\s*([a-z]+)=([0-9a-f]+)\s*\Z")


def derive_keys(token: str) -> tuple[bytes, bytes]:
    raw = token.encode("utf-8")
    return (hmac.new(raw, SERVER_LABEL, hashlib.sha256).digest(),
            hmac.new(raw, CLIENT_LABEL, hashlib.sha256).digest())


def address(host: str, port: int) -> str:
    return f"{host}:{int(port)}"


def server_proof(k_s: bytes, cn: str, sn: str, host: str, port: int) -> str:
    message = "\n".join(("hello.v1", cn, sn, address(host, port))).encode("ascii")
    return hmac.new(k_s, message, hashlib.sha256).hexdigest()


def signature(k_c: bytes, method: str, path: str, body: bytes, ts: int, nonce: str,
              sn: str, host: str, port: int) -> str:
    digest = hashlib.sha256(body).hexdigest()
    message = "\n".join((method.upper(), path, digest, str(int(ts)), nonce, sn,
                         address(host, port))).encode("utf-8")
    return hmac.new(k_c, message, hashlib.sha256).hexdigest()


def auth_header(k_c: bytes, method: str, path: str, body: bytes, ts: int, nonce: str,
                sn: str, host: str, port: int) -> str:
    sig = signature(k_c, method, path, body, ts, nonce, sn, host, port)
    return f"{SCHEME} v=1, ts={int(ts)}, nonce={nonce}, sn={sn}, sig={sig}"


def parse_header(value: str) -> dict | None:
    """The fields of an FW-Sig header, or None when anything is off."""
    if type(value) is not str or not value.startswith(SCHEME + " ") or len(value) > 512:
        return None
    fields = {}
    for part in value[len(SCHEME) + 1:].split(","):
        match = _FIELD.fullmatch(part)
        if match is None or match.group(1) in fields:
            return None
        fields[match.group(1)] = match.group(2)
    if set(fields) != {"v", "ts", "nonce", "sn", "sig"} or fields["v"] != "1":
        return None
    if not (_HEX16.fullmatch(fields["nonce"]) and _HEX16.fullmatch(fields["sn"])
            and _HEX32.fullmatch(fields["sig"]) and fields["ts"].isdigit()
            and len(fields["ts"]) <= 12):
        return None
    return {**fields, "ts": int(fields["ts"])}


def is_nonce(value) -> bool:
    return type(value) is str and _HEX16.fullmatch(value) is not None


def is_digest(value) -> bool:
    return type(value) is str and _HEX32.fullmatch(value) is not None


def same(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("ascii", "replace"), b.encode("ascii", "replace"))


def commitment(kind: str, salt: bytes, text: str) -> str:
    """sha256(tag || 0x00 || 32-byte salt || utf8(text)): binds the text and
    reveals nothing without the salt, which is deleted with the turn."""
    if len(salt) != 32:
        raise ValueError("salt must be 32 bytes")
    return hashlib.sha256(_COMMIT_TAGS[kind] + b"\x00" + salt + text.encode("utf-8")).hexdigest()
