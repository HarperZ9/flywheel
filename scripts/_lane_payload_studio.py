"""Put a lane's Studio runtime dependencies on the generator's import path.

accountable-surface imports coherence_membrane and proof_surface. The frozen
build stages both from the pinned Studio runtime payload
(``packaging/studio-runtime-sources.json``), so the generator imports them from
the same pins: each component's listed files at its pinned ref, read from the
sibling checkout the lane registry names in ``extra_source_repos``, with every
file hash checked against the Studio manifest. An installed copy of either
package can no longer stand in for the pin.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from _lane_payload_slice import requirement_import_name
from _lane_payload_source import _ROOT, GeneratorError, _filtered_bytes, _hash_bytes

STUDIO_SOURCES = _ROOT / "packaging" / "studio-runtime-sources.json"


def _components() -> dict[str, Any]:
    try:
        return json.loads(STUDIO_SOURCES.read_text(encoding="utf-8"))["components"]
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        raise GeneratorError(f"studio runtime sources unreadable: {exc}") from exc


def _checkout_for(component: dict[str, Any], lane: Any, checkout_root: Path) -> Path:
    repo_name = str(component["repo"]).rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
    for rel in lane.extra_source_repos:
        if Path(rel).name == repo_name:
            return checkout_root / rel
    raise GeneratorError(
        f"lane {lane.name!r} imports Studio component {repo_name!r} but names no "
        "checkout for it in extra_source_repos")


def _write_component(component: dict[str, Any], checkout: Path, dest: Path) -> None:
    ref = str(component["ref"])
    subdir = str(component.get("source_subdir") or "")
    hashes = component["manifest"].get("file_hashes", {})
    for rel in component["manifest"]["files"]:
        git_path = f"{subdir}/{rel}" if subdir else rel
        data = _filtered_bytes(checkout, ref, git_path)
        expected = hashes.get(rel)
        if expected is None or _hash_bytes(data) != f"sha256:{expected}":
            raise GeneratorError(f"studio component file {rel} does not match its pinned hash")
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def studio_dependency_root(
    lane: Any, pkg: str, deps: list[str], checkout_root: Path,
) -> tuple[Path | None, list[str]]:
    """(import root, package names) for the lane's Studio-supplied dependencies.

    Returns (None, []) when the lane needs none. The caller removes the root."""
    components = _components()
    names = [n for n in (requirement_import_name(d) for d in deps) if n in components and n != pkg]
    if not names:
        return None, []
    root = Path(tempfile.mkdtemp(prefix="flywheel_lane_studio_"))
    for name in names:
        component = components[name]
        _write_component(component, _checkout_for(component, lane, checkout_root), root)
    return root, names
