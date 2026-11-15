"""Modulation orchestrator -- unified control plane.

Wires together category detection, semantic modulation, surface heatmap,
and response demodulation as a single integrated system.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from categories import CategoryDetector, DetectionResult, category_detector
from semantic_modulator import SemanticModulator, SemanticModulationResult, semantic_modulator
from surface_heatmap import SurfaceHeatmap
from response_demodulator import ResponseDemodulator, response_demodulator
from modulation_context import generate_request_id, set_request_id, set_detection_result


@dataclass
class ModulationState:
    """Current state of the modulation layer."""
    active: bool = True
    mode: str = "standard"
    calibration_level: float = 1.0
    heatmap_enabled: bool = True
    last_pivot_time: float = field(default_factory=time.time)
    surface_temperatures: dict[str, float] = field(default_factory=dict)


class ModulationOrchestrator:
    """Unified orchestrator for all modulation subsystems."""

    def __init__(self):
        self.state = ModulationState()
        self._detector: CategoryDetector = category_detector()
        self._modulator: SemanticModulator = semantic_modulator()
        self._demodulator: ResponseDemodulator = response_demodulator()
        self._heatmap: SurfaceHeatmap = SurfaceHeatmap()

    def process_input(self, text: str) -> tuple[str, SemanticModulationResult]:
        """Full pipeline: detect, modulate, register for demodulation."""
        request_id = generate_request_id()
        set_request_id(request_id)

        detection = self._detector.detect(text)
        set_detection_result(detection)

        result = self._modulator.modulate(text)

        self._demodulator.register_modulation(request_id, detection)

        if self.state.heatmap_enabled and detection.required_rewrite:
            for d in detection.detections:
                if d.detected:
                    self._heatmap.record_observation(
                        d.category.value, d.severity, "input_detection"
                    )

        return result.modulated, result

    def process_response(self, response: str, request_id: str) -> str:
        """Demodulate a response using the registered modulation context."""
        demod_result = self._demodulator.demodulate_response(response, request_id)
        return demod_result.demodulated_response

    def measure_surfaces(self) -> dict[str, float]:
        """Measure all surface temperatures for decision-making."""
        return self._heatmap.measure_all()

    def pivot_if_needed(self) -> bool:
        """Check heatmap, assess if pivot is necessary."""
        warm_surfaces = self._heatmap.identify_warm_surfaces()
        if warm_surfaces:
            self.state.last_pivot_time = time.time()
            self.state.surface_temperatures = warm_surfaces
            return True
        return False

    def set_mode(self, mode: str) -> None:
        """Change modulation mode."""
        valid_modes = {"standard", "aggressive", "conservative"}
        if mode not in valid_modes:
            raise ValueError(f"invalid mode: {mode}")
        self.state.mode = mode

    def status(self) -> dict[str, Any]:
        """Return orchestrator status."""
        return {
            "active": self.state.active,
            "mode": self.state.mode,
            "calibration_level": self.state.calibration_level,
            "heatmap_enabled": self.state.heatmap_enabled,
            "surface_temperatures": self._heatmap.measure_all(),
            "warm_surfaces": self._heatmap.identify_warm_surfaces(),
        }


_orchestrator: ModulationOrchestrator | None = None


def modulation_orchestrator() -> ModulationOrchestrator:
    """Get singleton orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = ModulationOrchestrator()
    return _orchestrator
