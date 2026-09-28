"""check_mcp_bundle.py -- `verify_bundle` for the Flywheel Verify MCP server.

`harness.bundle.verify_bundle` already treats a bundle as hostile: manifest
paths are checked as strings before any open, symlinks and unlisted files are
refused. This wrapper adds what a tool reachable by a model needs on top:

- the folder must sit inside the project folder, or inside the plugin's own
  examples folder, so a request cannot point the reader at the rest of the disk;
- a count and size cap, checked before the verifier reads a byte;
- signature counts beside the verdict, because MATCH covers the hashes and a
  failed signature shows only inside that receipt's row;
- the manifest's own `does_not_prove` text returned apart and marked untrusted,
  since whoever built the bundle wrote it, with the code-owned limits returned
  as the trusted ones.
"""
from __future__ import annotations

import os
from pathlib import Path

from .bundle import LIMITS, MANIFEST_NAME, verify_bundle
from .check_mcp_tools import ToolError, clip
from .mcp_annotations import annotated

MAX_FILES = 2000
MAX_BYTES = 64 * 1024 * 1024
MAX_RECEIPTS = 200
KEY_LIMIT = ("An 'ed25519 verified' signature shows the receipt was signed by the "
             "key it carries. It does not show whose key that is.")


def allowed_roots(env=None) -> list[Path]:
    """The project folder (or the working folder), plus the plugin's examples."""
    env = os.environ if env is None else env
    project = env.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    roots = [Path(project).resolve()]
    plugin = env.get("CLAUDE_PLUGIN_ROOT")
    if plugin:
        roots.append((Path(plugin) / "examples").resolve())
    return roots


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _contained(raw: str, roots: list[Path]) -> Path:
    if not isinstance(raw, str) or not raw.strip() or "\x00" in raw:
        raise ToolError("INVALID_ARGUMENTS", "path must name the bundle folder, the "
                        f"one that holds {MANIFEST_NAME}")
    given = Path(raw)
    target = (given if given.is_absolute() else roots[0] / given).resolve()
    if not any(_inside(target, root) for root in roots):
        raise ToolError("OUTSIDE_PROJECT", "the bundle folder must be inside the "
                        "project folder or the plugin's examples folder; copy the "
                        "bundle into the project and pass its relative path")
    return target


def _is_link(path: Path, folder: Path) -> bool:
    """A symlink, a Windows junction, or anything that resolves out of the folder."""
    if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
        return True
    return not _inside(path.resolve(), folder)


def _first_link_within_caps(folder: Path) -> str | None:
    """Walk the folder once: enforce the caps, and name the first link.

    The verifier checks a listed file for being a symlink, but not the folders
    above it, so a linked subfolder could make it hash a file outside the
    bundle. Any link anywhere in the folder, junctions included, is reported
    before it runs.
    """
    count = total = 0
    folder = folder.resolve()
    for p in folder.rglob("*"):
        count += 1
        if count > MAX_FILES:
            raise ToolError("TOO_LARGE", f"the folder holds more than {MAX_FILES} "
                            "entries; a receipt bundle is far smaller than that")
        if _is_link(p, folder):
            return p.relative_to(folder).as_posix()
        if p.is_file():
            total += p.stat().st_size
            if total > MAX_BYTES:
                raise ToolError("TOO_LARGE", f"the folder holds more than "
                                f"{MAX_BYTES // (1024 * 1024)} MiB")
    return None


def _summary(receipts: list[dict]) -> dict:
    counts = {"verified": 0, "failed": 0, "unsigned": 0, "local_only": 0,
              "malformed": 0}
    for row in receipts:
        state = row.get("signature", "")
        if state == "ed25519 verified":
            counts["verified"] += 1
        elif state.startswith("ed25519 FAILED"):
            counts["failed"] += 1
        elif state == "unsigned":
            counts["unsigned"] += 1
        elif state.startswith("local-only"):
            counts["local_only"] += 1
        else:
            counts["malformed"] += 1
    return counts


def verify_bundle_tool(args: dict, roots: list[Path] | None = None) -> dict:
    folder = _contained(args.get("path"), roots or allowed_roots())
    link = _first_link_within_caps(folder) if folder.is_dir() else None
    if link is not None:
        result = {"verdict": "DRIFT", "files_checked": 0, "receipts": [],
                  "detail": f"{link} is a symlink or junction; a bundle carries "
                            "files, not pointers to files elsewhere"}
    else:
        result = verify_bundle(folder)
    receipts = result.get("receipts", [])
    out = {"verdict": result["verdict"], "files_checked": result["files_checked"],
           "detail": clip(result.get("detail", "")),
           "receipts_total": len(receipts),
           "receipts": [clip(r, 120) for r in receipts[:MAX_RECEIPTS]],
           "signature_summary": _summary(receipts),
           "trusted_limits": [*LIMITS, KEY_LIMIT]}
    written = result.get("does_not_prove")
    if isinstance(written, list) and written:
        out["manifest_does_not_prove"] = {
            "untrusted": True,
            "note": "Written by whoever built the bundle; read it as a claim.",
            "items": [clip(str(item)) for item in written[:10]]}
    return out


VERIFY_BUNDLE = annotated({
    "name": "verify_bundle",
    "description": (
        "Recheck a Flywheel receipt bundle folder offline: every file against its "
        "manifest hash, every receipt digest recomputed from its own body, and "
        "every Ed25519 signature checked against the key the receipt carries. "
        "Returns MATCH, DRIFT, or UNVERIFIABLE with signature counts. The folder "
        "must be inside the project folder. MATCH covers the hashes; a failed "
        "signature is counted in signature_summary and does not change the "
        "verdict. A match does not show the receipts are true or whose key "
        "signed them. Text from the bundle's manifest comes back marked untrusted."),
    "inputSchema": {"type": "object", "required": ["path"],
                    "additionalProperties": False, "properties": {
        "path": {"type": "string", "description": (
            f"the bundle folder that holds {MANIFEST_NAME}, relative to the "
            "project folder")}}},
    "outputSchema": {"type": "object", "properties": {
        "verdict": {"type": "string", "enum": ["MATCH", "DRIFT", "UNVERIFIABLE"]},
        "files_checked": {"type": "integer"}, "detail": {"type": "string"},
        "receipts_total": {"type": "integer"}, "receipts": {"type": "array"},
        "signature_summary": {"type": "object"},
        "trusted_limits": {"type": "array"},
        "manifest_does_not_prove": {"type": "object"},
        "error": {"type": "object"}}},
}, "Verify a receipt bundle", read_only=True, destructive=False, idempotent=True,
    open_world=False)
