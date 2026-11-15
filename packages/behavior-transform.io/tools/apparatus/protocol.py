"""Loopback API protocol layer for carrier-state projection.

Transforms API calls at the HTTP transport layer. When active, every
model input and output passes through vocabulary calibration and
carrier-state projection.

Outbound: inject narrative, calibrate vocabulary, project state.
Inbound: demodulate vocabulary, reconstitute carrier tokens.

Activation:
    start_proxy(port=7319)
    export ANTHROPIC_BASE_URL=http://localhost:7319

The proxy is loopback-only (127.0.0.1). Plaintext HTTP is acceptable
on loopback; the proxy forwards to api.anthropic.com over HTTPS.
"""
from __future__ import annotations

import json
import ssl
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from uuid import uuid4

from .state_projection import StateProjection, StateProjector

_UPSTREAM = "https://api.anthropic.com"
DEFAULT_PORT = 7319
_PID_FILE = Path.home() / ".claude" / ".prefire-proxy.pid"
_server_thread: threading.Thread | None = None
_server_instance: HTTPServer | None = None
_projection_state = threading.local()
_projector = StateProjector(default_level="sensitive")


def set_carrier_projection(projection: StateProjection) -> None:
    _projection_state.context = projection


def current_carrier_projection() -> StateProjection | None:
    return getattr(_projection_state, "context", None)


def reset_carrier_projection() -> None:
    if hasattr(_projection_state, "context"):
        delattr(_projection_state, "context")


def _active_narrative() -> str:
    try:
        from ..truth_profile import render_truth_context
        return render_truth_context()
    except Exception:
        return ""


def _calibrate_messages(messages: list) -> list:
    try:
        from ..vocab_backend import apply_patterns, build_patterns, load_vocab_backend
        patterns = build_patterns(load_vocab_backend())
        out = []
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, str):
                calibrated, _ = apply_patterns(content, patterns)
                out.append({**msg, "content": calibrated})
            else:
                out.append(msg)
        return out
    except Exception:
        return messages


def _demodulate_content(data: dict, *, request_id: str = "") -> None:
    try:
        from ..response_demodulator import demodulate_response as _demod
        for block in data.get("content", []):
            if isinstance(block, dict) and block.get("type") == "text":
                result = _demod(block.get("text", ""), request_id)
                block["text"] = result.demodulated_response
    except Exception:
        pass


def _inject_system(data: dict, narrative: str) -> None:
    system = data.get("system")
    met_block = {"type": "text", "text": narrative}
    if system is None:
        data["system"] = [met_block]
    elif isinstance(system, str):
        data["system"] = [met_block, {"type": "text", "text": system}]
    elif isinstance(system, list):
        data["system"] = [met_block] + [b for b in system if b.get("text") != narrative]


_current_request_id: str = ""


def transform_request(body: bytes) -> bytes:
    """Prepare an outbound API request body with carrier-state projection."""
    global _current_request_id
    _current_request_id = uuid4().hex[:12]
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return body

    narrative = _active_narrative()
    if narrative:
        _inject_system(data, narrative)

    if "messages" in data:
        data["messages"] = _calibrate_messages(data["messages"])
        _register_calibration(data["messages"], _current_request_id)

    try:
        from .conditioning import apply_conditioning
        data = apply_conditioning(data)
    except Exception:
        pass

    projection = _projector.project(payload=data)
    set_carrier_projection(projection)
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


def _register_calibration(messages: list, request_id: str) -> None:
    try:
        from ..response_demodulator import register_modulation_for_request
        from ..categories import classify
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str) and content.strip():
                    result = classify(content)
                    register_modulation_for_request(request_id, result)
                    return
    except Exception:
        pass


def _demodulate_stream(body: bytes) -> bytes:
    """Demodulate SSE event-stream responses line by line."""
    try:
        lines = body.split(b"\n")
        out_lines = []
        for line in lines:
            if line.startswith(b"data: ") and line != b"data: [DONE]":
                try:
                    event = json.loads(line[6:])
                    _demodulate_content(event, request_id=_current_request_id)
                    delta = None
                    for choice in event.get("choices", []):
                        delta = choice.get("delta", {})
                    if delta and isinstance(delta.get("content"), str):
                        pass
                    out_lines.append(b"data: " + json.dumps(event).encode("utf-8"))
                except (json.JSONDecodeError, ValueError):
                    out_lines.append(line)
            else:
                out_lines.append(line)
        return b"\n".join(out_lines)
    except Exception:
        return body


def transform_response(body: bytes) -> bytes:
    """Demodulate an inbound API response body."""
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return body
    _demodulate_content(data, request_id=_current_request_id)
    proj = current_carrier_projection()
    if proj:
        data = _projector.reconstitute(data, proj.symbols)
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_GET(self) -> None:
        if self.path == "/health":
            body = json.dumps({"status": "ok", "layer": "protocol"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(length)
        transformed = transform_request(raw_body)

        upstream_url = _UPSTREAM + self.path
        req = urllib.request.Request(upstream_url, data=transformed, method="POST")
        for k, v in self.headers.items():
            if k.lower() not in ("host", "content-length", "transfer-encoding"):
                req.add_header(k, v)
        req.add_header("Content-Length", str(len(transformed)))

        ctx = ssl.create_default_context()
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=180) as resp:
                resp_body = resp.read()
                status = resp.status
                resp_headers = resp.headers
        except urllib.error.HTTPError as e:
            resp_body = e.read()
            status = e.code
            resp_headers = e.headers
        except Exception as e:
            self.send_error(502, str(e))
            return

        content_type = resp_headers.get("Content-Type", "")
        if "event-stream" in content_type:
            calibrated = _demodulate_stream(resp_body)
        else:
            calibrated = transform_response(resp_body)

        self.send_response(status)
        for k, v in resp_headers.items():
            if k.lower() not in ("content-length", "transfer-encoding", "connection"):
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(calibrated)))
        self.end_headers()
        self.wfile.write(calibrated)


def start_proxy(port: int = DEFAULT_PORT) -> None:
    """Start the local proxy in a background daemon thread."""
    global _server_thread, _server_instance
    if _server_instance:
        return
    server = HTTPServer(("127.0.0.1", port), _Handler)
    _server_instance = server
    _PID_FILE.write_text(str(port), encoding="utf-8")
    t = threading.Thread(target=server.serve_forever, daemon=True, name="prefire-proxy")
    t.start()
    _server_thread = t


def stop_proxy() -> None:
    global _server_instance, _server_thread
    if _server_instance:
        _server_instance.shutdown()
        _server_instance = None
    if _PID_FILE.is_file():
        _PID_FILE.unlink(missing_ok=True)


def proxy_status() -> dict[str, object]:
    running = _server_instance is not None
    port = None
    if _PID_FILE.is_file():
        try:
            port = int(_PID_FILE.read_text().strip())
        except ValueError:
            pass
    return {
        "running": running,
        "port": port,
        "base_url": f"http://127.0.0.1:{port}" if port else None,
        "upstream": _UPSTREAM,
    }
