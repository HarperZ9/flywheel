"""desktop_status.py -- the read-only desktop connection-status route.

The desktop shell needs typed connection facts, not one boolean: online
versus degraded versus an incompatible client, with the lane summary
alongside. This module serves exactly those facts under the versioned
schema flywheel.desktop-status/v1. Missing roster fields degrade to
honest zeros; nothing here mutates state and nothing echoes secrets.
"""
from __future__ import annotations

SCHEMA = "flywheel.desktop-status/v1"

#: Bumped when a route the desktop depends on changes its contract. A
#: desktop built against a newer API level reads `compatible: false` and
#: renders version_mismatch instead of guessing.
API_VERSION = 1


def desktop_status(lanes: dict, *, client_api: int = API_VERSION) -> dict:
    """Fixed connection facts for the desktop shell.

    `lanes` is the lane roster ({n_lanes, by_status}); missing fields
    degrade to zeros. A client claiming a newer api level than this
    gateway serves reads `status: incompatible`.
    """
    by_status = lanes.get("by_status") if isinstance(lanes, dict) else None
    total = lanes.get("n_lanes", 0) if isinstance(lanes, dict) else 0
    live = by_status.get("live", 0) if isinstance(by_status, dict) else 0
    total = total if isinstance(total, int) and total >= 0 else 0
    live = live if isinstance(live, int) and 0 <= live <= total else 0
    compatible = isinstance(client_api, int) and client_api <= API_VERSION
    if not compatible:
        state = "incompatible"
    elif live < total:
        state = "degraded"
    else:
        state = "ok"
    return {
        "schema": SCHEMA,
        "status": state,
        "api_version": API_VERSION,
        "lanes_live": live,
        "lanes_total": total,
        "compatible": compatible,
    }
