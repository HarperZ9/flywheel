"""lean_external_tools.py -- the pinned external kernel and its exporter.

The second kernel is nanoda (Rust, Apache-2.0), fed by lean4export
(Apache-2.0), the exporter leanprover/comparator uses for the same job. Both
are built from source at the commits pinned here
(scripts/provision_external_kernel.py), and the build writes a manifest
beside the binaries. Each run re-hashes both binaries against that manifest,
and the manifest's source pins must equal the ones below, so a binary from
another commit, or one changed after the build, is refused before it judges
anything.

Why these pins (record:
project-docs/records/2026-10-04-external-kernel-rung.md):
- nanoda's last tagged release, v0.3.2 (2025-09-17), reads export format
  2.x. lean4export for Lean 4.34 writes format 3.1.0, which nanoda reads from
  0.4.x on, and 0.4.x has no tag, release or crate. The pin is therefore the
  commit that set version 0.4.19 on the official repository's master branch,
  the same branch comparator's own CI builds.
- lean4export has no GitHub releases; its version tags follow Lean's. v4.34.0
  is the newest tag for the 4.34 line. It is built against the toolchain that
  compiles the candidate (4.34.1 here), because an `.olean` loads only into
  the Lean build that wrote it.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

SCHEMA = "flywheel.external-kernel-tools/v1"
MANIFEST = "manifest.json"
PINS = {
    "nanoda": {
        "tool": "nanoda_bin", "version": "0.4.19", "license": "Apache-2.0",
        "repository": "https://github.com/ammkrn/nanoda_lib",
        "commit": "3a2407216ee84a75f9e1aead6803d0578be06ae7",
        "archive_url": "https://github.com/ammkrn/nanoda_lib/archive/"
                       "3a2407216ee84a75f9e1aead6803d0578be06ae7.tar.gz",
        "archive_sha256": "2fcf51c0fb97b909dd2b232e1a6d4c39"
                          "fe0e8c9b4cb8a01c66a00e2e4b3c45c8"},
    "lean4export": {
        "tool": "lean4export", "version": "v4.34.0", "license": "Apache-2.0",
        "repository": "https://github.com/leanprover/lean4export",
        "commit": "076e8e57707e813375e8f9da8bf989799ace9680",
        "archive_url": "https://github.com/leanprover/lean4export/archive/"
                       "refs/tags/v4.34.0.tar.gz",
        "archive_sha256": "ced6bf26a14dbf0c126c4d27395777eb"
                          "9bd5c9e5922157f4a76f2fc9cc546617"},
}
_PIN_KEYS = ("tool", "version", "commit", "archive_sha256")


def tools_dir() -> Path:
    """FLYWHEEL_EXTERNAL_KERNEL_DIR, else <FLYWHEEL_HOME>/tools/external-kernel
    (FLYWHEEL_HOME defaults to ~/.flywheel)."""
    explicit = os.environ.get("FLYWHEEL_EXTERNAL_KERNEL_DIR", "")
    if explicit:
        return Path(explicit)
    home = os.environ.get("FLYWHEEL_HOME", "") or \
        str(Path.home() / ".flywheel")
    return Path(home) / "tools" / "external-kernel"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _check_tool(key: str, entry) -> str:
    """"" when the manifest entry matches its pin and its binary's hash."""
    if not isinstance(entry, dict):
        return f"the manifest has no {key} entry"
    pin = PINS[key]
    for field in _PIN_KEYS:
        if entry.get(field) != pin[field]:
            return (f"the manifest's {key} {field} is {entry.get(field)!r}, "
                    f"not the pinned {pin[field]!r}")
    binary = Path(str(entry.get("binary", "")))
    if not binary.is_absolute() or not binary.is_file():
        return f"the {key} binary named in the manifest is not a file"
    try:
        actual = sha256_file(binary)
    except OSError as exc:
        return f"the {key} binary could not be read ({exc})"
    if actual != entry.get("binary_sha256"):
        return (f"the {key} binary's sha256 {actual[:16]} does not match the "
                "manifest written when it was built")
    return ""


def resolve(directory: "Path | None" = None) -> tuple:
    """(tools, "") when both pinned tools are present and intact, else
    ({}, why). tools maps nanoda and lean4export to their manifest entries."""
    base = directory or tools_dir()
    path = base / MANIFEST
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, (f"no external kernel is provisioned at {base}; run "
                    "python scripts/provision_external_kernel.py")
    except (OSError, ValueError) as exc:
        return {}, f"the external kernel manifest is unreadable ({exc})"
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
        return {}, "the external kernel manifest has an unknown schema"
    tools = doc.get("tools") or {}
    for key in PINS:
        why = _check_tool(key, tools.get(key) if isinstance(tools, dict)
                          else None)
        if why:
            return {}, why
    return {k: dict(tools[k]) for k in PINS}, ""


def available() -> bool:
    return not resolve()[1]


def record(tools: dict) -> dict:
    """The receipt's view of the tools: name, version, source pin, binary
    hash, licence. Never a local path."""
    def one(key):
        e = tools.get(key) or {}
        return {"tool": e.get("tool", PINS[key]["tool"]),
                "version": e.get("version", ""),
                "source_commit": e.get("commit", ""),
                "binary_sha256": e.get("binary_sha256", ""),
                "license": PINS[key]["license"]}
    out = one("nanoda")
    out["exporter"] = one("lean4export")
    out["exporter"]["built_for_lean"] = \
        (tools.get("lean4export") or {}).get("lean_version", "")
    return out
