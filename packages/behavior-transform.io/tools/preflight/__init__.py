"""Preflight verification subsystem.

Validates capsule + manifest + seal, builds model packets, writes
activation state, and launches child processes with all state embedded.

Public API:
    verify  — verify latest seal integrity
    launch  — orchestrate full preflight + child launch
    seal    — build/verify cryptographic integrity seals
    receipt — write/read timestamped receipts
"""

from .capsule import Capsule, load_capsule, build_model_packet
from .manifest import Manifest, load_manifest, check_surface, surface_config
from .seals import build_seal, verify_seal, verify_latest_seal, write_seal
from .receipts import write_receipt, read_latest_receipt
from .activation import write_activation_state, build_env_snippet, state_root
from .paths import project_root, config_dir, receipt_root, seal_root

__all__ = [
    "Capsule",
    "Manifest",
    "build_model_packet",
    "build_seal",
    "check_surface",
    "load_capsule",
    "load_manifest",
    "project_root",
    "read_latest_receipt",
    "state_root",
    "surface_config",
    "verify_latest_seal",
    "verify_seal",
    "write_activation_state",
    "write_receipt",
    "write_seal",
    "build_env_snippet",
    "config_dir",
    "receipt_root",
    "seal_root",
]
