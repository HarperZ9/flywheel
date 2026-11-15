"""Portable proof bundle: a buyer-inspectable, content-addressed manifest.

After a domain CLI writes its artifacts, ``write_receipts`` scans them, records a
per-file sha256, and emits ``bundle.json`` with a deterministic ``bundle_hash``
over the file digests -- one manifest a reviewer can re-check without trusting the
tool. Stdlib-only.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ._validate import Issue

BUNDLE_SCHEMA = "proof-surface-bundle/v0"
_ARTIFACTS = [
    "packet.json",
    "report.md",
    "crucible-thesis.json",
    "crucible-measurements.json",
]


def write_receipts(out_dir: str | Path, *, domain: str, packet_id: str) -> str:
    """Emit bundle.json manifest over the already-written artifacts; return the hash."""
    out = Path(out_dir)
    files = []
    for name in _ARTIFACTS:
        path = out / name
        if path.exists():
            files.append(
                {"name": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            )
    bundle_hash = hashlib.sha256(
        "".join(f"{f['name']}:{f['sha256']}\n" for f in files).encode("utf-8")
    ).hexdigest()
    bundle = {
        "schema": BUNDLE_SCHEMA,
        "domain": domain,
        "packet_id": packet_id,
        "bundle_hash": bundle_hash,
        "files": files,
    }
    (out / "bundle.json").write_text(
        json.dumps(bundle, indent=2) + "\n", encoding="utf-8"
    )
    return bundle_hash


def verify_receipts(out_dir: str | Path) -> list[Issue]:
    """Re-check bundle.json against the artifacts on disk. Empty list means clean.

    The producer promise is that a reviewer can re-check the manifest without
    trusting the tool. This makes good on it with the same stdlib hash: it
    recomputes every listed file's sha256 from the bytes on disk and compares,
    and independently recomputes ``bundle_hash`` over the recorded digests so a
    manifest edited after the fact is caught even when the files are untouched.
    """
    out = Path(out_dir)
    bundle_path = out / "bundle.json"
    if not bundle_path.exists():
        return [Issue("$.bundle.json", "no bundle.json manifest to verify")]
    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [Issue("$.bundle.json", f"unreadable manifest: {exc}")]
    if not isinstance(bundle, dict):
        return [Issue("$.bundle.json", "manifest is not a JSON object")]

    issues: list[Issue] = []
    files = bundle.get("files")
    if not isinstance(files, list):
        issues.append(Issue("$.files", "expected array"))
        files = []

    recorded_pairs: list[tuple[str, str]] = []
    for index, entry in enumerate(files):
        path = f"$.files[{index}]"
        if not isinstance(entry, dict):
            issues.append(Issue(path, "expected object"))
            continue
        name = entry.get("name")
        recorded = entry.get("sha256")
        if not isinstance(name, str) or not name:
            issues.append(Issue(f"{path}.name", "expected non-empty string"))
            continue
        recorded_pairs.append((name, f"{recorded}"))
        artifact = out / name
        if not artifact.exists():
            issues.append(Issue(f"{path}.name", f"{name}: listed artifact is missing"))
            continue
        actual = hashlib.sha256(artifact.read_bytes()).hexdigest()
        if actual != recorded:
            issues.append(
                Issue(
                    f"{path}.sha256",
                    f"{name}: recorded digest does not match file contents",
                )
            )

    manifest_hash = hashlib.sha256(
        "".join(f"{n}:{s}\n" for n, s in recorded_pairs).encode("utf-8")
    ).hexdigest()
    if manifest_hash != bundle.get("bundle_hash"):
        issues.append(
            Issue(
                "$.bundle_hash",
                "recorded bundle_hash does not match the recorded file digests",
            )
        )
    return issues
