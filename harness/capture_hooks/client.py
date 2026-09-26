"""The hook side of the capture channel (7.1, I18).

Order of checks, each ending the call with a reason code on failure:
the endpoint file the gateway wrote after binding (no file, or a process that
is not running: GATEWAY_NOT_RUNNING, and no connection at all); a literal
loopback host (anything else: REMOTE_NOT_SUPPORTED); the listener owner check;
a hello that carries no credential and no body, answered with a proof bound
to the connected address (SERVER_PROOF_FAILED otherwise). Only then does a
request with a body go out, signed, never carrying the token.
"""
from __future__ import annotations

import http.client
import json
import secrets
import socket
import time
from pathlib import Path

from . import listener_owner, protocol

ENDPOINT_SCHEMA = "flywheel.gateway-endpoint/v1"
_MAX_RESPONSE = 1024 * 1024


class CaptureFailure(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def read_token(home: Path) -> str:
    path = Path(home) / "gateway.token"
    try:
        token = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        raise CaptureFailure("TOKEN_MISSING") from None
    except (OSError, UnicodeError):
        raise CaptureFailure("TOKEN_UNREADABLE") from None
    if not token:
        raise CaptureFailure("TOKEN_MISSING")
    return token


def read_endpoint(home: Path) -> dict:
    try:
        doc = json.loads((Path(home) / "gateway.endpoint").read_bytes())
    except (OSError, ValueError):
        raise CaptureFailure("GATEWAY_NOT_RUNNING") from None
    if (type(doc) is not dict or doc.get("schema") != ENDPOINT_SCHEMA
            or type(doc.get("port")) is not int or not 0 < doc["port"] < 65536
            or type(doc.get("pid")) is not int or type(doc.get("host")) is not str):
        raise CaptureFailure("GATEWAY_NOT_RUNNING")
    if doc["host"] not in protocol.LOOPBACK:
        raise CaptureFailure("REMOTE_NOT_SUPPORTED")
    if not listener_owner.pid_alive(doc["pid"]):
        raise CaptureFailure("GATEWAY_NOT_RUNNING")
    return doc


class Channel:
    """One proved connection target. `hello` must succeed before `request`."""

    def __init__(self, endpoint: dict, token: str, timeout: float) -> None:
        self.host, self.port, self.pid = endpoint["host"], endpoint["port"], endpoint["pid"]
        self.k_s, self.k_c = protocol.derive_keys(token)
        self.timeout, self.sn, self.effective = timeout, None, {}

    def _exchange(self, method: str, path: str, body: bytes | None, headers: dict):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            return response.status, response.read(_MAX_RESPONSE + 1)
        except socket.timeout:
            raise CaptureFailure("TIMEOUT") from None
        except (OSError, http.client.HTTPException):
            raise CaptureFailure("GATEWAY_UNREACHABLE") from None
        finally:
            connection.close()

    def hello(self) -> dict:
        refused = listener_owner.check_listener(self.host, self.port, self.pid)
        if refused:
            raise CaptureFailure(refused)
        cn = secrets.token_hex(16)
        status, raw = self._exchange("GET", f"{protocol.HELLO_PATH}?v=1&cn={cn}", None, {})
        try:
            doc = json.loads(raw) if status == 200 and len(raw) <= _MAX_RESPONSE else None
        except ValueError:
            doc = None
        if (type(doc) is not dict or not protocol.is_nonce(doc.get("sn"))
                or not protocol.is_digest(doc.get("proof"))):
            raise CaptureFailure("SERVER_PROOF_FAILED")
        expected = protocol.server_proof(self.k_s, cn, doc["sn"], self.host, self.port)
        if not protocol.same(expected, doc["proof"]):
            raise CaptureFailure("SERVER_PROOF_FAILED")
        self.sn = doc["sn"]
        self.effective = doc.get("effective") if type(doc.get("effective")) is dict else {}
        return self.effective

    def request(self, method: str, path: str, payload=None) -> dict:
        if self.sn is None:
            raise CaptureFailure("SERVER_PROOF_FAILED")
        body = b"" if payload is None else json.dumps(payload).encode("utf-8")
        header = protocol.auth_header(self.k_c, method, path, body, int(time.time()),
                                      secrets.token_hex(16), self.sn, self.host, self.port)
        headers = {"Authorization": header}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        status, raw = self._exchange(method, path, body if payload is not None else None,
                                     headers)
        if status == 401:
            raise CaptureFailure("AUTH_REFUSED")
        if 400 <= status < 500:
            raise CaptureFailure(f"REQUEST_REJECTED:{status}")
        if status != 200:
            raise CaptureFailure(f"GATEWAY_ERROR:{status}")
        try:
            doc = json.loads(raw) if raw else {}
        except ValueError:
            raise CaptureFailure("GATEWAY_ERROR:200") from None
        return doc if type(doc) is dict else {}


def open_channel(home: Path, token: str, timeout: float) -> Channel:
    channel = Channel(read_endpoint(home), token, timeout)
    channel.hello()
    return channel
