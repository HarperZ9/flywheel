from __future__ import annotations

import os
from pathlib import Path

from .import_adapters import import_config
from .inspect_evidence_route import handle_inspect_get, handle_inspect_upload
from .store import put_entity


def handle_import_post(path: str, handler) -> tuple[dict, int] | None:
    if path == "/api/import/inspect":
        return handle_inspect_upload(handler)
    if path != "/api/import":
        return None
    req, bad = handler._req_json()
    if bad:
        return bad
    root, err = _resolve_import_root(handler, (req or {}).get("root"))
    if err:
        return {"error": err}, 400
    doc = import_config(root)
    try:
        doc["stored"] = put_entity("import-manifest", doc).get("eid", "")
    except Exception as exc:
        doc["stored"] = f"store unavailable: {type(exc).__name__}"
    return doc, 200


def handle_import_get(path: str, handler, query: str = "") -> tuple[dict, int] | None:
    return handle_inspect_get(path, handler, query)


def _resolve_import_root(handler, requested):
    default = Path(handler.root)
    if not requested:
        return default, None
    try:
        path = Path(str(requested)).expanduser().resolve()
    except (OSError, ValueError) as exc:
        return default, f"invalid root: {exc}"
    if not path.is_dir():
        return default, f"root is not an existing directory: {requested}"
    allow = [part for part in os.environ.get("FLYWHEEL_WORKSPACE_ROOTS", "").split(os.pathsep) if part.strip()]
    if allow:
        resolved = os.path.normcase(str(path))
        roots = [os.path.normcase(str(Path(part).expanduser().resolve())) for part in allow]
        if not any(resolved == root or resolved.startswith(root + os.sep) for root in roots):
            return default, f"root is not under an allowlisted workspace prefix: {requested}"
    return path, None
