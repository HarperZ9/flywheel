"""pack_admission.py -- admit a domain pack into run-root state.

Admission is verify-then-persist-then-witness: the shipped verifier
refuses anything that is not a clean data-only manifest, the admitted
manifest is written under <run_root>/packs/<pack_id>/ as immutable
state (a different pack_sha256 under a live pack_id refuses), and the
accountable hooks `pack.admitted` event fires from the run root's
registry so blocking automations bite here too.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .accountable_hooks import event_blocked, load_registry, run_hooks, \
    subprocess_runner
from .domain_pack import SCHEMA, verify_pack_manifest

ADMISSION_SCHEMA = "flywheel.domain-pack-admission/v1"
_PACK_ID = re.compile(r"^[a-z0-9][a-z0-9.-]{2,98}$")


def _refuse(msg: str) -> None:
    raise ValueError(msg)


def _pack_dir(run_root: Path, pack_id: str) -> Path:
    if not _PACK_ID.fullmatch(str(pack_id)):
        _refuse(f"pack_id is not a safe slug: {pack_id!r}")
    return Path(run_root) / "packs" / str(pack_id)


def _persist(admitted: dict, *, run_root: Path) -> Path:
    path = _pack_dir(run_root, admitted["pack_id"]) / "manifest.json"
    existing = None
    if path.is_file():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing.get("pack_sha256") != admitted["pack_sha256"]:
            _refuse("pack_id already admitted with different content; "
                    "admitted manifests are immutable -- bump the version")
    if existing is None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(admitted, indent=2, sort_keys=True),
                        encoding="utf-8")
    return path


def admit_pack(*, manifest: dict, fixtures_root, run_root,
               clock) -> dict:
    admitted = verify_pack_manifest(manifest, fixtures_root=fixtures_root)
    _persist(admitted, run_root=run_root)
    registry = load_registry(Path(run_root) / "hooks" / "registry.json")
    hook_receipts = run_hooks(
        "pack.admitted", registry,
        runner=subprocess_runner(timeout_s=15.0),
        context={"pack_id": admitted["pack_id"],
                 "version": admitted["version"],
                 "pack_sha256": admitted["pack_sha256"]})
    return {
        "schema": ADMISSION_SCHEMA,
        "pack_id": admitted["pack_id"],
        "version": admitted["version"],
        "pack_sha256": admitted["pack_sha256"],
        "state": admitted["state"],
        "admitted_at": clock(),
        "hook_receipts": hook_receipts,
        "event_blocked": event_blocked(hook_receipts),
    }


def list_admitted(run_root) -> list[dict]:
    root = Path(run_root) / "packs"
    rows = []
    if not root.is_dir():
        return rows
    for entry in sorted(root.iterdir()):
        path = entry / "manifest.json"
        if not path.is_file():
            continue
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if manifest.get("schema") != SCHEMA:
            _refuse("the admitted-pack store holds an unsealed row")
        rows.append(manifest)
    return rows
