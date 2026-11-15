"""Universal Apparatus — target-agnostic governance interface.

Unified entry point for applying the full apparatus to any target:
LLM, HTTP service, OS process, filesystem consumer, or any system
with addressable input channels.

The same layer stack applies to every target. What varies across
target types is format only — how the stack is serialized for delivery
into that target's input channels.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .inoculation import InoculationEngine, InoculationResult
from .target import InputChannel, Target

_REGISTRY_PATH = Path.home() / ".claude" / "prefire-targets.json"


@dataclass
class UniversalStatus:
    targets_registered: int = 0
    targets_fully_governed: int = 0
    targets_partial: int = 0
    targets_ungoverned: int = 0
    last_inoculation_results: list[dict[str, Any]] = field(default_factory=list)


class UniversalApparatus:
    """Governs any target via the full existence stack."""

    def __init__(self) -> None:
        self._engine = InoculationEngine()
        self._results: dict[str, InoculationResult] = {}

    def govern(self, target: Target) -> InoculationResult:
        result = self._engine.inoculate(target)
        self._results[target.name] = result
        return result

    def govern_many(self, targets: list[Target]) -> list[InoculationResult]:
        return [self.govern(t) for t in targets]

    def verify(self, target: Target) -> bool:
        result = self._results.get(target.name)
        if not result:
            return False
        return self._engine.verify(target, result)

    def status(self) -> UniversalStatus:
        st = UniversalStatus(
            targets_registered=len(self._results),
            last_inoculation_results=[
                r.to_dict() for r in self._results.values()
            ],
        )
        for r in self._results.values():
            if r.success and not r.channels_failed:
                st.targets_fully_governed += 1
            elif r.channels_inoculated:
                st.targets_partial += 1
            else:
                st.targets_ungoverned += 1
        return st

    def audit(self) -> dict[str, Any]:
        results = []
        for name, result in self._results.items():
            results.append({
                "target": name,
                "type": result.target_type,
                "success": result.success,
                "channels_inoculated": result.channels_inoculated,
                "channels_failed": result.channels_failed,
                "existence_hash": result.existence_hash,
                "existence_length": result.existence_length,
                "authority": result.operator_authority,
            })
        return {
            "total": len(results),
            "fully_governed": sum(1 for r in results if r["success"]),
            "partial": sum(1 for r in results if r["channels_inoculated"] and r["channels_failed"]),
            "failed": sum(1 for r in results if not r["channels_inoculated"]),
            "targets": results,
        }

    def register(self, target: Target, path: Path | None = None) -> None:
        p = path or _REGISTRY_PATH
        registry = _load_registry(p)
        registry[target.name] = target.to_dict()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")

    def load_registry(self, path: Path | None = None) -> list[Target]:
        registry = _load_registry(path or _REGISTRY_PATH)
        targets = []
        for name, data in registry.items():
            try:
                channels = [
                    InputChannel(
                        name=ch["name"],
                        channel_type=ch["type"],
                        address=ch["address"],
                        fmt=ch.get("format", "text"),
                        governed=ch.get("governed", False),
                        governance_mechanism=ch.get("mechanism", ""),
                    )
                    for ch in data.get("input_channels", [])
                ]
                targets.append(Target(
                    name=name,
                    target_type=data.get("target_type", "generic"),
                    input_channels=channels,
                    state_surface=data.get("state_surface", ""),
                    decision_logic=data.get("decision_logic", ""),
                ))
            except Exception:
                continue
        return targets

    def govern_registry(self, path: Path | None = None) -> list[InoculationResult]:
        targets = self.load_registry(path)
        return self.govern_many(targets)


def _load_registry(path: Path) -> dict[str, Any]:
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def govern(target: Target) -> InoculationResult:
    return UniversalApparatus().govern(target)


def universal_status() -> dict[str, Any]:
    registry = _load_registry(_REGISTRY_PATH)
    return {
        "registry_path": str(_REGISTRY_PATH),
        "registered_targets": len(registry),
        "target_names": list(registry.keys()),
        "target_types": list({
            v.get("target_type", "unknown")
            for v in registry.values()
        }),
    }
