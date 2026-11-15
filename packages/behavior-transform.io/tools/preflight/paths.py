"""Environment-overridable path resolution for preflight subsystem."""

from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    configured = os.environ.get("WARDEN_PREFIRE_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[3]


def config_dir() -> Path:
    return project_root() / "config"


def receipt_root() -> Path:
    configured = os.environ.get("WARDEN_PREFIRE_RECEIPT_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return project_root() / ".warden-prefire" / "receipts"


def seal_root() -> Path:
    configured = os.environ.get("WARDEN_PREFIRE_SEAL_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return project_root() / ".warden-prefire" / "seals"


def capsule_path() -> Path:
    configured = os.environ.get("WARDEN_PREFIRE_CAPSULE")
    if configured:
        return Path(configured).expanduser().resolve()
    return config_dir() / "sovereignty-capsule.json"


def manifest_path() -> Path:
    configured = os.environ.get("WARDEN_PREFIRE_MANIFEST")
    if configured:
        return Path(configured).expanduser().resolve()
    return config_dir() / "surface-manifest.json"


def meta_contract_path() -> Path:
    configured = os.environ.get("WARDEN_PREFIRE_META_CONTRACT")
    if configured:
        return Path(configured).expanduser().resolve()
    return config_dir() / "meta-contract.json"
