"""Coarse GPU telemetry from nvidia-smi: power draw and utilization only.

The query names exactly two fields, so no process name, memory content or
workload detail is ever read. Readings are coarsened into bands before they
leave this module. Conforming heartbeats exclude power and utilization figures;
the device model therefore carries this reading only in the non-conforming
telemetry profile.
"""

from __future__ import annotations

import subprocess

from harness import safe_program

QUERY = ["--query-gpu=power.draw,utilization.gpu", "--format=csv,noheader,nounits"]
POWER_BAND_W = 50
UTIL_BAND_PCT = 25


def read_raw() -> dict:
    """One reading. Raises RuntimeError with the reason when none is available."""
    if safe_program.which("nvidia-smi") is None:
        raise RuntimeError("nvidia-smi not found on PATH")
    cmd, env = safe_program.launch(["nvidia-smi", *QUERY])
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=10)
    if proc.returncode != 0:
        raise RuntimeError(f"nvidia-smi exit {proc.returncode}: {proc.stderr.strip()[:200]}")
    first = proc.stdout.strip().splitlines()[0]
    power_s, util_s = [part.strip() for part in first.split(",")]
    return {"power_w": float(power_s), "util_pct": int(util_s)}


def coarse(raw: dict) -> dict:
    """Band the reading: power to 50 W steps, utilization to 25 percent steps."""
    power_band = int(raw["power_w"] // POWER_BAND_W) * POWER_BAND_W
    util_band = min(100, int(raw["util_pct"] // UTIL_BAND_PCT) * UTIL_BAND_PCT)
    return {"power_band_w": power_band, "power_band_width_w": POWER_BAND_W,
            "util_band_pct": util_band, "util_band_width_pct": UTIL_BAND_PCT}


def read_coarse() -> dict | None:
    try:
        return coarse(read_raw())
    except (RuntimeError, OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return None
