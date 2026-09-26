"""The capture channel routes: hello, ping, prompt and stop (7.1, 7.2).

The hello takes no credential and answers with a proof bound to the address
the gateway bound, plus the capture settings in effect. Every other capture
route needs a request signed under a key derived from the token, checked
before any body is parsed. Prompt and stop bodies carry the client, the
session id, the prompt key and either a commitment with its salt or, when
content capture is in effect, the text. Content the settings do not allow is
dropped here, whatever the hook sent.
"""
from __future__ import annotations

import base64
import json
import re

from harness.capture_hooks import protocol
from harness.gateway_auth import _host_of
from harness.gateway_request_sig import STATE

MAX_CAPTURE_BODY = 4 * 1024 * 1024
REFUSED = {"schema": "flywheel.evidence-transport-error/v1",
           "error": {"code": "AUTH_REQUIRED", "message": "gateway authentication is required"}}
_SESSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_FIELDS = {"client", "session_id", "prompt_key", "commitment", "salt", "text",
           "stop_hook_active"}


def error(code: str, message: str) -> dict:
    return {"schema": "flywheel.evidence-transport-error/v1",
            "error": {"code": code, "message": message}}


def _bound(handler) -> tuple[str, int]:
    host, port = handler.server.server_address[:2]
    return host, port


def host_ok(handler) -> bool:
    return _host_of(handler.headers) in handler.allowed_hosts


def _owner(handler) -> str:
    from harness.operation_grants import load_or_create_owner_ref
    return load_or_create_owner_ref(handler.flywheel_home)


def effective(handler) -> dict:
    from harness.trace_capture_settings import effective as settings_in_effect
    return settings_in_effect(handler.flywheel_home, _owner(handler))


def hello(handler, qs: str):
    from urllib.parse import parse_qs
    if not handler.auth_token:
        return handler._json(error("CAPTURE_UNAVAILABLE", "the gateway has no token"), 503)
    cn = (parse_qs(qs).get("cn") or [""])[0]
    host, port = _bound(handler)
    body = STATE.hello(handler.auth_token, cn, host, port)
    if body is None:
        return handler._json(error("INVALID_REQUEST", "hello refused"), 429)
    return handler._json({**body, "effective": effective(handler)})


def signed_body(handler, method: str):
    """(raw body, None) when the signature holds, else (None, response sent)."""
    raw = b""
    if method == "POST":
        length = handler._content_length()
        if length is None or length > MAX_CAPTURE_BODY:
            return None, handler._json(error("INVALID_REQUEST", "body too large"), 413)
        ctype = (handler.headers.get("Content-Type", "") or "").split(";", 1)[0].strip()
        if ctype.lower() != "application/json":
            return None, handler._json(REFUSED, 401)
        raw = handler.rfile.read(length)
    host, port = _bound(handler)
    if not STATE.verify(handler.auth_token, handler.headers.get("Authorization", ""),
                        method, handler.path, raw, host, port):
        return None, handler._json(REFUSED, 401)
    handler.owner_ref = _owner(handler)
    return raw, None


def _turn_fields(raw: bytes) -> dict | None:
    try:
        doc = json.loads(raw or b"{}")
    except ValueError:
        return None
    if type(doc) is not dict or not set(doc) <= _FIELDS:
        return None
    key, session = doc.get("prompt_key"), doc.get("session_id")
    salt = doc.get("salt")
    try:
        salt = base64.b64decode(salt, validate=True) if salt is not None else None
    except (ValueError, TypeError):
        return None
    ok = (doc.get("client") in ("claude-code", "codex")
          and (session is None or type(session) is str and _SESSION.fullmatch(session))
          and (key is None or type(key) is str and _KEY.fullmatch(key))
          and (doc.get("commitment") is None or protocol.is_digest(doc.get("commitment")))
          and (salt is None or len(salt) == 32)
          and (doc.get("text") is None or type(doc["text"]) is str)
          and type(doc.get("stop_hook_active", False)) is bool)
    return {**doc, "salt": salt} if ok else None


def _shape_ok(event: str, fields) -> bool:
    if fields is None:
        return False
    has_text, has_commit = fields.get("text") is not None, fields.get("commitment") is not None
    if has_text and has_commit or has_commit and fields.get("salt") is None:
        return False
    return has_text or has_commit or event == "stop"  # a stop may carry no answer


def turn(handler, event: str, raw: bytes):
    import os
    from harness.trace_turn_store import TurnStore
    fields = _turn_fields(raw)
    if not _shape_ok(event, fields):
        return handler._json(error("INVALID_REQUEST", "malformed turn"), 422)
    settings = effective(handler)
    store = TurnStore(handler.flywheel_home, handler.owner_ref, settings=settings)
    text = fields.get("text") if settings["content"] == "on" else None
    if fields.get("text") is not None and text is None:
        # Content capture is off: keep only a commitment made here, never the text.
        fields["salt"] = os.urandom(32)
        fields["commitment"] = protocol.commitment(
            "prompt" if event == "prompt" else "answer", fields["salt"], fields["text"])
    args = (fields["client"], fields.get("session_id"), fields.get("prompt_key"))
    kwargs = {"commitment": None if text is not None else fields.get("commitment"),
              "salt": None if text is not None else fields.get("salt"), "text": text}
    if event == "prompt":
        store.prompt(*args, **kwargs)
        return handler._json({"schema": "flywheel.capture-turn-result/v1", "ok": True})
    result = store.stop(*args, **kwargs, stop_hook_active=fields.get("stop_hook_active", False))
    return handler._json({"schema": "flywheel.capture-turn-result/v1", "eid": result["eid"],
                          "pairing": result["pairing"], "segment": result["segment"]})


def freeze(handler, raw: bytes):
    from harness.trace_turn_store import TurnStore
    try:
        doc = json.loads(raw or b"{}")
    except ValueError:
        doc = None
    urls = doc.get("urls") if type(doc) is dict else None
    fields = _turn_fields(json.dumps({k: v for k, v in doc.items() if k != "urls"}).encode()
                          ) if type(doc) is dict else None
    if (fields is None or type(urls) is not list or len(urls) > 5
            or any(type(u) is not str or len(u) > 2048 for u in urls)):
        return handler._json(error("INVALID_REQUEST", "malformed freeze"), 422)
    settings = effective(handler)
    if settings["freeze_urls"] != "on":
        return handler._json(error("FREEZE_OFF", "URL freezing is not in effect"), 403)
    store = TurnStore(handler.flywheel_home, handler.owner_ref, settings=settings)
    manifest = store.freeze(fields["client"], fields.get("session_id"),
                            fields.get("prompt_key"), urls)
    return handler._json({"schema": "flywheel.capture-freeze-manifest/v1", **manifest})


def session(handler, raw: bytes):
    """Import one ended session by client and id; the gateway finds the file."""
    from harness.trace_import_session import SessionRefused, prepare, queue
    try:
        doc = json.loads(raw or b"{}")
    except ValueError:
        doc = None
    if (type(doc) is not dict or not set(doc) <= {"client", "session_id", "reason"}
            or type(doc.get("reason", "")) is not str or len(doc.get("reason", "")) > 64):
        return handler._json(error("INVALID_REQUEST", "client and session id only"), 422)
    if effective(handler)["archive_transcripts"] != "on":
        return handler._json(error("ARCHIVE_OFF", "transcript archiving is not in effect"), 403)
    try:
        root, path = prepare(doc.get("client"), doc.get("session_id"))
    except SessionRefused as refused:
        return handler._json(error(refused.code, "session not imported"), refused.status)
    queue(handler.flywheel_home, handler.owner_ref, doc["client"], doc["session_id"], root,
          path)
    return handler._json({"schema": "flywheel.capture-session-import/v1", "queued": True},
                         202)
