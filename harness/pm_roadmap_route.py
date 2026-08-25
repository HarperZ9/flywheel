"""pm_roadmap_route.py -- GET /api/pm/roadmap.

Read-only: the roadmap is assembled from sealed receipts on every
request; nothing here writes or admits.
"""
from __future__ import annotations

from pathlib import Path

from .evidence_public import TransportError, error_response
from .pm_roadmap import render_markdown, roadmap_from_run_root


def handle_pm_get(path: str, *, run_root, clock=None) -> tuple[dict, int]:
    if path == "/api/pm/roadmap":
        roadmap = roadmap_from_run_root(Path(run_root))
        return {"roadmap": roadmap,
                "one_page": render_markdown(roadmap)}, 200
    return error_response(TransportError("NOT_FOUND",
                                         "unknown pm route", 404))
