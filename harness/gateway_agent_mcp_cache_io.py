"""Atomic storage for backend-owned MCP discovery receipts."""
from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from .evidence_json import canonical_bytes
from .gateway_agent_mcp_cache_validation import CACHE_DIR_NAME, receipt_path
from .journey_lock import ExclusiveJourneyLock, fsync_directory
from .operation_grants import _secure_owner_only

def _write_receipt(state_root: Path, owner_ref: str, catalog_ref: str, receipt: dict) -> None:
    path = receipt_path(state_root, owner_ref, catalog_ref, receipt["receipt_sha256"])
    root = state_root / CACHE_DIR_NAME
    catalog_dir = path.parent
    root.mkdir(parents=True, exist_ok=True)
    _secure_owner_only(state_root, directory=True)
    _secure_owner_only(root, directory=True)
    owner_dir = root / owner_ref
    owner_dir.mkdir(exist_ok=True)
    _secure_owner_only(owner_dir, directory=True)
    catalog_dir.mkdir(exist_ok=True)
    _secure_owner_only(catalog_dir, directory=True)
    with ExclusiveJourneyLock.acquire(owner_dir / ".lock"):
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as stream:
                _secure_owner_only(temporary, directory=False)
                stream.write(canonical_bytes(receipt))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            _secure_owner_only(path, directory=False)
            with path.open("r+b") as stream:
                os.fsync(stream.fileno())
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
        for directory in (catalog_dir, owner_dir, root, state_root):
            fsync_directory(directory)
