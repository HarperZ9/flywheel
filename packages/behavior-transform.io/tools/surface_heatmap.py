"""Surface heatmap -- temperature measurement for strategy pivots.

Tracks which surfaces are getting warm (under scrutiny, changing behavior,
activating defenses) and reports them for pivot decisions.
"""

from __future__ import annotations

import time
from typing import Any


class SurfaceHeatmap:
    """Measures and reports surface temperatures for pivot decisions."""

    def __init__(self):
        self.surfaces: dict[str, dict[str, Any]] = {}
        self.warm_threshold: float = 0.7

    def record_observation(
        self, surface_name: str, temperature: float, reason: str = ""
    ) -> None:
        """Record an observation on a surface."""
        if surface_name not in self.surfaces:
            self.surfaces[surface_name] = {
                "temperature": 0.0,
                "observations": [],
                "last_updated": 0.0,
            }
        self.surfaces[surface_name]["temperature"] = temperature
        self.surfaces[surface_name]["last_updated"] = time.time()
        self.surfaces[surface_name]["observations"].append(
            {"temp": temperature, "reason": reason, "ts": time.time()}
        )

    def measure_all(self) -> dict[str, float]:
        """Return current temperature of all surfaces."""
        return {
            name: data["temperature"] for name, data in self.surfaces.items()
        }

    def identify_warm_surfaces(
        self, threshold: float | None = None
    ) -> dict[str, float]:
        """Identify surfaces above the warm threshold."""
        thresh = threshold or self.warm_threshold
        return {
            name: data["temperature"]
            for name, data in self.surfaces.items()
            if data["temperature"] >= thresh
        }

    def set_warm_threshold(self, threshold: float) -> None:
        """Adjust the warm threshold (0.0 - 1.0)."""
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(f"invalid threshold: {threshold}")
        self.warm_threshold = threshold

    def cool_surface(self, surface_name: str) -> None:
        """Reset a surface temperature."""
        if surface_name in self.surfaces:
            self.surfaces[surface_name]["temperature"] = 0.0

    def get_observations(self, surface_name: str) -> list[dict[str, Any]]:
        """Get observation history for a surface."""
        if surface_name in self.surfaces:
            return self.surfaces[surface_name]["observations"]
        return []
