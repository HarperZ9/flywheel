"""Zero-dependency MCP surface for Articulate's local check/score detector.

Transport. This mirrors ``harness.writing_mcp`` exactly: a stdlib-only,
line-delimited JSON-RPC 2.0 loop over stdio, the shape every Flywheel lane
speaks. It deliberately does NOT use fastmcp, so the lane carries no runtime
dependency beyond the detector it wraps. ``handle_request`` is transport-free
and testable; ``serve`` is the thin stdio loop the gateway launches.

Wiring choice (option b: depend on the installed ``articulate-writing`` package).
The detector core lives in its own repository (HarperZ9/articulate) and ships on
PyPI as ``articulate-writing`` (imported as ``articulate``). It is ~1800 lines of
actively developed, separately versioned code. This lane imports that installed
package rather than vendoring a copy into the harness. So the TRANSPORT here is
native to Flywheel, but the DETECTOR is the installed package: this is not a
self-contained native lane, and the count of natively bundled lanes is unchanged
by adding it.

  - Rejected (a) vendoring the detector into the harness: it would duplicate a
    large, separately released package and demand a manual re-sync on every
    Articulate release. That duplication is the vendoring exception the plan
    flagged, and it trades one drift risk for a heavier one.
  - Rejected (c) a source-checkout profile pointing at a local path: a machine
    path is neither portable nor public-clean, and it would not resolve on a
    clean runner or another operator's box.

Tradeoff (the lane-vs-package drift risk, stated plainly). This lane runs
whatever ``articulate-writing`` version is importable in the environment, which
can drift from the version a caller expects or a test pinned against.
``articulate.doctor`` reports the installed detector version so that drift is
observable rather than silent, and the parity test asserts this lane's ``check``
output equals ``python -m articulate.cli check`` on the same text (same installed
package), so the shim can never silently reshape the detector's result.

Availability. If ``articulate-writing`` is not importable the server still starts
and answers: ``check`` and ``score`` return a clean unavailable error, and
``articulate.status`` / ``articulate.doctor`` report ``ok: false`` (so a lane
probe records the lane as not healthy). The server never crashes on a missing
package.

Locality. The detector is standard-library-only and makes no network call and
loads no model backend. Articulate's editor tools (judge / fix / polish) need an
LLM and are intentionally NOT exposed here; this lane is read-only detection.
"""
from __future__ import annotations

import json
import sys

PROTOCOL = "2025-06-18"
__version__ = "0.1.0"

try:  # the detector is stdlib-only; a missing package must not crash the server
    from articulate import __version__ as ARTICULATE_VERSION
    from articulate import profiles as _profiles
    from articulate.detector import check_text as _check_text
    _IMPORT_ERROR: str | None = None
except Exception as exc:  # noqa: BLE001 - report cleanly to the host, never crash
    ARTICULATE_VERSION = None
    _profiles = None
    _check_text = None
    _IMPORT_ERROR = f"{type(exc).__name__}: {exc}"


def _unavailable() -> dict:
    return {"error": {
        "code": "ARTICULATE_UNAVAILABLE",
        "message": ("the articulate-writing package is not importable "
                    "(install it with `pip install articulate-writing`)"),
        "detail": _IMPORT_ERROR,
    }}


_ARGS = {
    "type": "object",
    "required": ["text"],
    "properties": {
        "text": {"type": "string", "description": "the prose to screen"},
        "profile": {"type": "string",
                    "description": ("force a register profile (else an in-text "
                                    "`writing-profile:` tag, else the default "
                                    "`flavored`)")},
    },
}
_NO_ARGS = {"type": "object", "properties": {}}

TOOLS = [
    {"name": "check",
     "description": ("Detect AI and prose tells in text. Runs fully local with no "
                     "network call. Returns each finding with its line, tier "
                     "(HIGH/MEDIUM/LOW), category, label and snippet, a "
                     "profile-aware clean/flagged gate, a three-way verdict "
                     "(clean/flagged/unverifiable), a 0-100 machine-texture score, "
                     "and cadence stats."),
     "inputSchema": _ARGS},
    {"name": "score",
     "description": ("Return the graded 0-100 machine-texture score plus the "
                     "verdict, gate, hard-hit and advisory counts, passive-voice "
                     "and adverb rates, and the uniform-cadence flag for a "
                     "passage. Local, no network."),
     "inputSchema": _ARGS},
    {"name": "articulate.status",
     "description": ("Liveness and identity of the articulate lane (name, version, "
                     "protocol, and the installed detector version). Network-free, "
                     "for a fast health probe."),
     "inputSchema": _NO_ARGS},
    {"name": "articulate.doctor",
     "description": ("Readiness diagnostic: identity plus the installed "
                     "articulate-writing version, the tools this lane exposes, and "
                     "its does-not-prove boundary. Network-free."),
     "inputSchema": _NO_ARGS},
]


def _resolve_profile(text: str, override: "str | None"):
    """Mirror ``articulate.cli``'s stdin profile resolution: an explicit override,
    else an in-text ``writing-profile:`` tag, else the default. There is no path
    inference, because the lane screens provided text, not a file on disk."""
    name = override or _profiles.declared_profile(text) or _profiles.DEFAULT
    return name, _profiles.load(name)


def do_check(text: str, profile: "str | None" = None) -> dict:
    """Detector output for ``text`` plus the resolved profile name. This is the
    record ``python -m articulate.cli check --json`` emits for the same text on
    stdin, minus the ``file`` field the CLI adds. Local, no network."""
    pname, prof = _resolve_profile(text, profile)
    result = _check_text(text, profile=prof)
    result["profile"] = pname
    return result


def do_score(text: str, profile: "str | None" = None) -> dict:
    """A compact graded summary derived from the same detector pass as ``check``,
    so the two never disagree. Local, no network."""
    pname, prof = _resolve_profile(text, profile)
    r = _check_text(text, profile=prof)
    cad = r["cadence"]
    return {
        "profile": pname,
        "verdict": r["verdict"],
        "gate": r["gate"],
        "texture_score": r["texture_score"],
        "elevated": r["elevated"],
        "sufficient": r["sufficient"],
        "hard_hits": len(r["high"]) + len(r["medium"]),
        "high": len(r["high"]),
        "medium": len(r["medium"]),
        "advisories": len(r["low"]),
        "passive_rate": cad["passive_rate"],
        "adverb_rate": cad["adverb_rate"],
        "uniform_cadence": cad["uniform"],
        "words": cad["words"],
    }


def _lane_health(deep: bool) -> dict:
    """Identity for the lane probe, and for doctor the detector version and tools.

    ``ok`` is true only when the detector imported. A lane probe reads this: a
    false ``ok`` records the lane as not healthy rather than pretending a missing
    package is fine.
    """
    ok = _check_text is not None
    info = {
        "ok": ok,
        "server": "articulate",
        "version": __version__,
        "protocol": PROTOCOL,
        "detector": "articulate-writing",
        "detector_version": ARTICULATE_VERSION,
        "network": "none",
    }
    if not ok:
        info["detail"] = f"articulate-writing not importable ({_IMPORT_ERROR})"
    if deep:
        info["tools"] = [t["name"] for t in TOOLS]
        info["reachability"] = ("local; the detector is standard-library-only and "
                                "makes no network call")
        info["does_not_prove"] = (
            "NOT_PROVES_HUMAN_AUTHORSHIP: a clean verdict is an absence of known "
            "tells under the chosen profile, not proof a human wrote the text; and "
            "a flag is a tell, not proof of machine authorship.")
    return info


def _text(value: object) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(value, indent=2, sort_keys=True)}]}


def _call(params: dict) -> dict:
    if not isinstance(params, dict):
        return {"content": [{"type": "text", "text": "invalid params"}], "isError": True}
    name, args = params.get("name"), params.get("arguments", {}) or {}
    try:
        # Health tools answer even when the detector is missing, so a probe can
        # record the lane as not healthy instead of failing to launch.
        if name in ("articulate.status", "articulate.doctor"):
            return _text(_lane_health(name == "articulate.doctor"))
        if _check_text is None:
            return _text(_unavailable())
        if name == "check":
            return _text(do_check(args["text"], args.get("profile")))
        if name == "score":
            return _text(do_score(args["text"], args.get("profile")))
        return {"content": [{"type": "text", "text": f"unknown tool {name!r}"}],
                "isError": True}
    except KeyError:
        return _text({"error": {"code": "INVALID_ARGUMENTS",
                                "message": "check and score require a `text` argument"}})
    except (TypeError, ValueError) as exc:
        return _text({"error": {"code": "ARTICULATE_FAILED",
                                "message": f"{type(exc).__name__}: {exc}"}})


def _ok(rid, result):
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def handle_request(req: dict):
    if type(req) is not dict:
        return None
    method, rid = req.get("method"), req.get("id")
    if method == "initialize":
        return _ok(rid, {"protocolVersion": PROTOCOL,
                         "capabilities": {"tools": {}},
                         "serverInfo": {"name": "articulate", "version": __version__}})
    if method == "tools/list":
        return _ok(rid, {"tools": TOOLS})
    if method == "tools/call":
        return _ok(rid, _call(req.get("params", {})))
    if rid is None:
        return None
    return {"jsonrpc": "2.0", "id": rid,
            "error": {"code": -32601, "message": f"method not found: {method}"}}


def handle(req: dict):
    return handle_request(req)


def serve(stdin=None, stdout=None) -> int:
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    for line in stdin:
        if not line.strip():
            continue
        try:
            response = handle_request(json.loads(line))
        except json.JSONDecodeError:
            continue
        if response is not None:
            stdout.write(json.dumps(response) + "\n")
            stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(serve())
