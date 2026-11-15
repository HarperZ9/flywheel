"""Apparatus — full-stack inference governance.

Ties pre-inference pipeline, vocabulary calibration, classification,
demodulation, conditioning, and target inoculation into a single
coherent interface.

Public API:
    from tools.apparatus import Apparatus, boot, BootResult
"""
from .boot import BootResult, boot, boot_status
from .orchestrator import Apparatus, ApparatusStatus

__all__ = [
    "Apparatus",
    "ApparatusStatus",
    "BootResult",
    "boot",
    "boot_status",
]
