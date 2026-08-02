"""run_bom.py -- Artifact 18: Model/Tool/Permission Bill of Materials.

Captures the complete run configuration: model checkpoint, system prompt hash,
tool versions, tool scopes, credentials present, runtime image hash, compute/
time limits, environment dependency hashes. Bound to every run_id.

The ARCHIVE QUERY acceptance test: a qualified team can reconstruct the run
configuration without relying on institutional memory.
"""
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass, field
from typing import Any

SCHEMA = "flywheel.run-bom/v1"


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_bytes(obj: dict[str, Any]) -> bytes:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


@dataclass
class RunBOM:
    """The bill of materials for one agent run."""
    run_id: str
    model_name: str = ""
    model_checkpoint: str = ""
    system_prompt_hash: str = ""
    python_version: str = field(default_factory=lambda: sys.version.split()[0])
    tool_versions: dict[str, str] = field(default_factory=dict)
    tool_scopes: dict[str, list[str]] = field(default_factory=dict)
    credentials_present: list[str] = field(default_factory=list)  # names only
    runtime_image_hash: str = ""
    max_steps: int = 0
    max_tokens: int = 0
    temperature: float = 0.0
    safeguards_removed: list[str] = field(default_factory=list)
    dependency_hashes: dict[str, str] = field(default_factory=dict)
    harness_version: str = ""
    tadr_tier: str = ""  # TADR consequence tier: T1/T2/T3
    tadr_modifiers: list[str] = field(default_factory=list)  # P/B/R/D/A/I/F/H/S/E/G/X

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "schema": SCHEMA,
            "run_id": self.run_id,
            "model": {
                "name": self.model_name,
                "checkpoint": self.model_checkpoint,
                "system_prompt_hash": self.system_prompt_hash,
            },
            "runtime": {
                "python_version": self.python_version,
                "harness_version": self.harness_version,
                "runtime_image_hash": self.runtime_image_hash,
            },
            "tools": {
                "versions": dict(self.tool_versions),
                "scopes": {k: list(v) for k, v in self.tool_scopes.items()},
            },
            "credentials_present": list(self.credentials_present),
            "limits": {
                "max_steps": self.max_steps,
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
            },
            "safeguards_removed": list(self.safeguards_removed),
            "dependency_hashes": dict(self.dependency_hashes),
            "governance": {
                "tadr_tier": self.tadr_tier,
                "tadr_modifiers": list(self.tadr_modifiers),
            } if self.tadr_tier else {},
        }
        return d

    def seal_hash(self) -> str:
        return _sha256_hex(_canonical_bytes(self.to_dict()))

    def sealed(self) -> dict[str, Any]:
        d = self.to_dict()
        d["seal_hash"] = self.seal_hash()
        return d


def capture_system_prompt_hash(prompt: str) -> str:
    """Hash a system prompt for the BOM (never store the prompt itself)."""
    return _sha256_hex(prompt.encode("utf-8"))


def capture_tool_scope(tool_name: str, capabilities: list[str]) -> dict[str, list[str]]:
    """Record a tool's capability scope."""
    return {tool_name: list(capabilities)}


def default_flywheel_bom(run_id: str = "default") -> RunBOM:
    """Capture the BOM for a default Flywheel run."""
    return RunBOM(
        run_id=run_id,
        harness_version="0.3.0",
        tool_scopes={
            "read_file": ["builtin-read"],
            "write_file": ["builtin-write"],
            "edit_file": ["builtin-write"],
            "run": ["builtin-exec"],
            "list_dir": ["builtin-read"],
            "grep": ["builtin-read"],
        },
        max_steps=20,
        max_tokens=4096,
    )
