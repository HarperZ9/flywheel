"""desktop_status.py -- the read-only desktop connection-status route.

The desktop shell needs typed connection facts, not one boolean: online
versus degraded versus an incompatible client, with the lane summary
alongside. This module serves exactly those facts under the versioned
schema flywheel.desktop-status/v1. Readiness remains unknown when the
roster is incomplete; nothing mutates state or echoes secrets.
"""
from __future__ import annotations

SCHEMA = "flywheel.desktop-status/v1"

#: Bumped when a route the desktop depends on changes its contract. A
#: desktop built against a newer API level reads `compatible: false` and
#: renders version_mismatch instead of guessing.
API_VERSION = 1


def _recovery_summary(value: dict | None) -> dict:
    if not isinstance(value, dict):
        return {"limited": False}
    out = {"limited": False}
    for key in ("journeys", "gateway_operations"):
        item = value.get(key)
        if not isinstance(item, dict):
            continue
        limited = len(item.get("limited_refs") or [])
        out[key] = {
            "limited": bool(item.get("recovery_limited")),
            "limited_count": limited,
            "diagnostic_count": len(item.get("diagnostic_refs") or []),
        }
        out["limited"] = out["limited"] or out[key]["limited"] or bool(limited)
    return out


def desktop_status(lanes: dict, *, client_api: int = API_VERSION,
                   startup_recovery: dict | None = None) -> dict:
    """Fixed connection facts for the desktop shell.

    `ok` means the engine responds without a known lane failure. Declared
    runtimes have not been probed. Legacy count fields retain zero defaults;
    lane_readiness explicitly distinguishes unknown and empty inventories.
    """
    by_status = lanes.get("by_status") if isinstance(lanes, dict) else None
    total = lanes.get("n_lanes", 0) if isinstance(lanes, dict) else 0
    live = by_status.get("live", 0) if isinstance(by_status, dict) else 0
    counts = {key: by_status.get(key, 0) for key in
              ("live", "declared", "missing", "stale")} if isinstance(by_status, dict) else {}
    complete = (isinstance(lanes, dict) and "n_lanes" in lanes
                and type(total) is int and total >= 0 and bool(counts)
                and all(type(v) is int and v >= 0 for v in counts.values())
                and sum(counts.values()) == total
                and set(by_status).issubset(counts))
    total = total if type(total) is int and total >= 0 else 0
    live = live if type(live) is int and 0 <= live <= total else 0
    readiness = "unknown"
    if complete:
        readiness = ("empty" if total == 0 else "unprobed" if counts["declared"]
                     else "unavailable" if counts["missing"] == total
                     else "partial" if counts["missing"] else "probed")
    compatible = isinstance(client_api, int) and client_api <= API_VERSION
    recovery = _recovery_summary(startup_recovery)
    if not compatible:
        state = "incompatible"
    elif recovery["limited"]:
        state = "degraded"
    elif complete and (counts["missing"] or counts["stale"]):
        state = "degraded"
    else:
        state = "ok"
    return {
        "schema": SCHEMA,
        "status": state,
        "api_version": API_VERSION,
        "lanes_live": live,
        "lanes_total": total,
        "lane_readiness": readiness,
        **{f"lanes_{key}": counts[key] if complete else None
           for key in ("declared", "missing", "stale")},
        "compatible": compatible,
        "startup_recovery": recovery,
    }
