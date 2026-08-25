"""pack_admission_route.py -- pack admission routes.

GET  /api/packs        list admitted packs (run-root state)
POST /api/packs/admit  verify, persist, and witness an admission
"""
from __future__ import annotations

from pathlib import Path

from .evidence_public import TransportError, error_response
from .pack_admission import admit_pack, list_admitted


def _invalid(message: str) -> tuple[dict, int]:
    return error_response(TransportError("INVALID_REQUEST", message, 422))


def handle_pack_get(path: str, *, run_root) -> tuple[dict, int]:
    if path == "/api/packs":
        rows = list_admitted(Path(run_root))
        return {"schema": "flywheel.pack-list/v1",
                "packs": rows, "count": len(rows)}, 200
    return error_response(TransportError("NOT_FOUND",
                                         "unknown pack route", 404))


def handle_pack_post(path: str, body: dict, *, run_root,
                     clock=None) -> tuple[dict, int]:
    action = path.rsplit("/", 1)[-1]
    if action != "admit":
        return error_response(TransportError("NOT_FOUND",
                                             "unknown pack route", 404))
    if not isinstance(body, dict) or not isinstance(body.get("manifest"),
                                                    dict):
        return _invalid("the admission carries no manifest")
    fixtures_root = body.get("fixtures_root") or "."
    try:
        ack = admit_pack(manifest=body["manifest"],
                         fixtures_root=fixtures_root,
                         run_root=Path(run_root),
                         clock=clock or (lambda: ""))
    except ValueError as exc:
        return _invalid(str(exc))
    return ack, 200
