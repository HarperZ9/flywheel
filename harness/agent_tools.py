"""agent_tools.py -- the harness's verification economy as callable tools.

Any connected model can call these through a provider's native tools
field: prove a receipt's inclusion in the Merkle log, summarize the
receipts ledger, read the world root hash. Tools that carry receipts
are the surface no other coding harness ships. Dispatchers are strict:
unknown names, non-dict arguments, and malformed leaves return typed
fixed errors, never guesses and never internal tracebacks.
"""
from __future__ import annotations

from pathlib import Path

from . import gateway as _gateway
from .receipt_proof import build_receipt_proof
from .run_paths import run_root_default
from .transparency_log import verify_inclusion


def tool_definitions() -> list[dict]:
    """The registry in OpenAI tools format; every provider lane can
    present these verbatim."""
    return [
        {"type": "function", "function": {
            "name": "verify_receipt_inclusion",
            "description": (
                "Prove one receipt (a 64-hex sha256 envelope digest) is in "
                "the Merkle receipts log, with an offline-recheckable proof "
                "object. Returns included true/false plus the proof."),
            "parameters": {"type": "object", "properties": {
                "leaf": {"type": "string",
                         "description": "64-hex sha256 envelope digest"}},
                "required": ["leaf"]}}},
        {"type": "function", "function": {
            "name": "receipts_ledger_summary",
            "description": ("Counts from the receipts ledger: envelopes, "
                            "accepted passes, catalog presence."),
            "parameters": {"type": "object", "properties": {}}}},
        {"type": "function", "function": {
            "name": "world_root_hash",
            "description": ("The world state root: a sha256 over the "
                            "receipt catalog, so any file change moves it."),
            "parameters": {"type": "object", "properties": {}}}},
    ]


def _ledger(root, run_root) -> dict:
    return _gateway.receipts_ledger(root, run_root)


def _world(root) -> dict:
    return _gateway.world_state(root)


def dispatch(name: str, arguments, *, ledger=None, world=None,
             root: Path | None = None, run_root: Path | str | None = None,
             world_root: str | None = None) -> dict:
    """Run one tool by name. `ledger`/`world` are injectable providers for
    tests; production reads the live gateway substrate (the repo root and
    the default run root)."""
    if not isinstance(arguments, dict):
        return {"error": "arguments must be a JSON object"}
    root = root if root is not None else _gateway.REPO
    run_root = run_root if run_root is not None else run_root_default()
    ledger = ledger or (lambda **_: _ledger(root, run_root))
    world = world or (lambda **_: _world(root))
    try:
        if name == "verify_receipt_inclusion":
            return _verify_inclusion(arguments, ledger)
        if name == "receipts_ledger_summary":
            if arguments:
                return {"error": "this tool takes no arguments"}
            led = ledger()
            return {"envelopes": led.get("envelope_count", 0),
                    "pass": led.get("pass_count", 0),
                    "catalog_present": led.get("catalog_present", 0),
                    "catalog_total": len(led.get("catalog", []))}
        if name == "world_root_hash":
            if arguments:
                return {"error": "this tool takes no arguments"}
            return {"root_hash": world_root if world_root is not None
                    else world().get("root_hash", "")}
        return {"error": f"unknown tool: {name}"}
    except Exception:
        # Fixed messages only: a tool result is a public surface.
        if name == "verify_receipt_inclusion":
            return {"error": "the receipts ledger could not be read"}
        if name == "world_root_hash":
            return {"error": "the world state could not be read"}
        return {"error": "the receipts ledger could not be read"}


def _verify_inclusion(args: dict, ledger) -> dict:
    leaf = args.get("leaf")
    if not isinstance(leaf, str) or len(leaf) != 64 \
            or any(c not in "0123456789abcdef" for c in leaf):
        return {"error": "leaf must be a 64-hex sha256 digest"}
    led = ledger()
    leaves = [e["sha256"] for e in led.get("envelopes", [])]
    try:
        proof = build_receipt_proof(leaf, leaves)
    except Exception:
        root = ""
        if leaves:
            from .transparency_log import merkle_root
            root = merkle_root(leaves)
        return {"included": False, "proof": {"leaf": leaf,
                                             "merkle_root": root}}
    return {"included": verify_inclusion(proof["leaf"],
                                         proof["audit_path"],
                                         proof["merkle_root"]),
            "proof": proof}
