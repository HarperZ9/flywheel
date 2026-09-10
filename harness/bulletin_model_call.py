"""One reserved Ollama invocation with durable evidence before backend parsing.

The caller must inject the reviewed strict transport. This wrapper adds budget
and capture checks; it is not itself a socket implementation or launch command.
"""
from __future__ import annotations

import ipaddress
import math
from urllib.parse import urlsplit

from .evidence_json import canonical_bytes, strict_load_json
from .local_usage import ollama_native_usage


class CallError(RuntimeError):
    pass


class OneGenerationTransport:
    def __init__(self, transport, store, *, reservation_id: str, stage_id: str,
                 origin: str, model: str, max_tokens: int):
        try:
            parsed = urlsplit(origin)
            valid = (parsed.scheme == "http" and parsed.port is not None
                     and ipaddress.ip_address(parsed.hostname).is_loopback
                     and not any((parsed.username, parsed.password, parsed.path, parsed.query, parsed.fragment)))
        except (ValueError, TypeError):
            valid = False
        if (not valid or not callable(transport) or type(max_tokens) is not int
                or not 0 < max_tokens <= 512 or type(model) is not str or not model
                or type(reservation_id) is not str or not reservation_id
                or type(stage_id) is not str):
            raise CallError("invalid_invocation_policy")
        self.transport, self.store = transport, store
        self.reservation_id, self.stage_id = reservation_id, stage_id
        self.origin, self.model, self.max_tokens = origin, model, max_tokens
        self.failed = self.post_entered = self.health_entered = self.response_received = False

    def _put(self, name, data, limit):
        try:
            return self.store.put(name, data, max_bytes=limit)
        except Exception as exc:
            self.failed = True
            raise CallError("capture_sink_failed") from exc

    def _admit(self, method, url, body, timeout):
        if self.failed or type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
            raise CallError("invocation_stopped_or_invalid_timeout")
        if method == "GET":
            if (self.stage_id != "readiness" or self.health_entered or self.post_entered
                    or url != self.origin + "/api/tags" or body is not None):
                raise CallError("health_not_admitted")
            return min(timeout, 5.0)
        if method != "POST" or url != self.origin + "/api/chat" or self.post_entered:
            raise CallError("generation_not_admitted")
        try:
            obj = strict_load_json(body, max_bytes=262144, max_depth=16)
            tokens = obj.get("options", {}).get("num_predict")
            valid = (set(obj) == {"model", "messages", "stream", "options"}
                     and obj["model"] == self.model and obj["stream"] is False
                     and type(obj["messages"]) is list and type(tokens) is int
                     and 0 < tokens <= self.max_tokens)
        except (ValueError, TypeError, AttributeError):
            valid = False
        if not valid:
            raise CallError("request_not_admitted")
        return min(timeout, 60.0)

    def __call__(self, method, url, body, timeout):
        timeout = self._admit(method, url, body, timeout)
        metadata = method == "GET"
        prefix = "health-" if metadata else ""
        self._put(prefix + "request.json", canonical_bytes({
            "reservation_id": self.reservation_id, "stage_id": self.stage_id,
            "method": method, "url": url, "timeout_seconds": timeout,
            "generation_max_tokens": None if metadata else self.max_tokens}), 8192)
        if not metadata:
            self._put("request.bin", body, 262144)
        # Mark before invoking transport: no retry even when delivery is unknown.
        if metadata:
            self.health_entered = True
        else:
            self.post_entered = True
        try:
            status, response = self.transport(method, url, body, timeout)
        except BaseException:
            self.failed = True
            raise
        if not metadata:
            self.response_received = True
        try:
            text = None
            if type(response) is dict and type(response.get("message")) is dict:
                text = response["message"].get("content")
            text_valid = type(text) is str
            record = {"reservation_id": self.reservation_id, "stage_id": self.stage_id,
                      "capture_kind": "parsed_response_not_wire", "status": status,
                      "parsed_response": response,
                      "assistant_text_state": "available" if text_valid else "invalid_or_missing",
                      "usage": ollama_native_usage(response) if type(response) is dict and not metadata else None}
            self._put(prefix + "response.json", canonical_bytes(record), 2097152)
            if text_valid and not metadata:
                self._put("assistant.txt", text.encode("utf-8", "strict"), 1048576)
        except BaseException:
            self.failed = True
            raise
        return status, response


def execute_backend_once(transport: OneGenerationTransport, backend_call) -> dict:
    """Call an existing backend/gate once; capture, validity and delivery differ."""
    backend_result, failure = None, None
    try:
        backend_result = backend_call()
    except Exception as exc:
        failure = type(exc).__name__ if type(exc).__name__ in (
            "BackendError", "MalformedBackendOutput", "CallError") else "backend_call_failed"
    result = {"outcome": "unknown", "backend_valid": False, "text": None,
              "failure": failure, "backend_result": backend_result}
    if transport.failed:
        result["failure"] = "transport_or_capture_incomplete"
        return result
    if not transport.response_received:
        result["outcome"] = "no_send" if not transport.post_entered else "unknown"
        result["failure"] = failure or "generation_response_missing"
        return result
    try:
        capture = strict_load_json(transport.store.read("response.json", max_bytes=2097152),
                                   max_bytes=2097152, max_depth=20)
        message = capture["parsed_response"].get("message")
        text = message.get("content") if type(message) is dict else None
        result["outcome"] = "response_received"
        result["text"] = text if type(text) is str else None
        accepted, rejection = _accepted_backend_result(backend_result, transport, text)
        result["backend_valid"] = failure is None and type(text) is str and accepted
        result["failure"] = failure or ("invalid_assistant_text" if type(text) is not str else rejection)
    except Exception:
        transport.failed = True
        result["failure"] = "capture_recheck_failed"
    return result


def _accepted_backend_result(value, transport, text):
    """Honor the actual gate's returned disposition, including caught failures."""
    if type(value) is not dict:
        return False, "backend_result_missing"
    expected = f"ollama:{transport.model}"
    if transport.stage_id != "readiness":
        valid = (type(value.get("text")) is str and value["text"] == text
                 and value.get("model_ref") == expected)
        return valid, None if valid else "backend_result_rejected"
    row = value
    if value.get("schema") == "harness.model-endpoint-gate/v1":
        rows = value.get("rows")
        if (value.get("verdict") != "MODEL_ENDPOINT_GATE_PASS"
                or type(rows) is not list or len(rows) != 1):
            error = rows[0].get("error_type") if type(rows) is list and len(rows) == 1 and type(rows[0]) is dict else None
            return False, "MalformedBackendOutput" if error == "MalformedBackendOutput" else "readiness_rejected"
        row = rows[0]
    if type(row) is not dict:
        return False, "readiness_rejected"
    valid = (row.get("schema") == "harness.model-endpoint-gate.row/v1"
             and transport.health_entered and row.get("health_ok") is True
             and row.get("generation_ok") is True and row.get("failure_class") == ""
             and row.get("observed_model_ref") == expected and row.get("model_ref") == expected)
    error = "MalformedBackendOutput" if row.get("error_type") == "MalformedBackendOutput" else "readiness_rejected"
    return valid, None if valid else error
