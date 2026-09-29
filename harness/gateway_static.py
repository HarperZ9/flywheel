"""Serve supported web assets within a configured, operator-selected root."""
from pathlib import Path


_TYPES = {
    ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript",
    ".css": "text/css", ".json": "application/json", ".jsonl": "application/x-ndjson",
    ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp",
    ".ico": "image/x-icon", ".woff": "font/woff", ".woff2": "font/woff2",
    ".ttf": "font/ttf", ".wasm": "application/wasm",
}


def _hidden(path):
    return any(part.startswith(".") for part in path.parts)


def serve_static(handler, path: str):
    """Reject hidden paths, unsupported types, and resolved root escapes."""
    rel = path.replace("\\", "/").lstrip("/") or "site/index.html"
    if ":" in rel or any(part.startswith(".") for part in rel.split("/")):
        return handler._json({"error": "forbidden"}, 403)
    try:
        root = Path(handler.root).resolve()
        requested = root / rel
        if requested.is_dir():
            requested /= "index.html"
        target = requested.resolve()
        if not target.is_relative_to(root) or _hidden(target.relative_to(root)):
            return handler._json({"error": "forbidden"}, 403)
        ctype = _TYPES.get(target.suffix.lower())
        if requested.suffix.lower() not in _TYPES or ctype is None or not target.is_file():
            return handler._json({"error": "not found"}, 404)
        body = target.read_bytes()
    except (OSError, ValueError, RuntimeError):
        return handler._json({"error": "not found"}, 404)
    handler.send_response(200)
    handler.send_header("Content-Type", ctype)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
