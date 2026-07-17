"""telos_kernels.py: the telos creative engine, driven in place.

The telos lane's MCP surface catalogs its creative kernels; the kernels
themselves are executable modules in the lane's own source. This bridge
runs THAT code (never a reimplementation) through node, hands back the
kernel's own measurement and receipt hashes, and refuses by name when
the lane checkout or node is absent. Composition through the lane's
contract: flywheel gains the features, telos keeps the authorship.
"""
from __future__ import annotations

import json
import os
import subprocess

from .lanes import LANES, REPO

SCHEMA = "flywheel.telos-kernel-run/v1"

# kernels bridged so far: the pure-JSON geometry pair. The raster pair
# wants pixel buffers; that seam is named, not faked.
KERNELS = {
    "plotter.harmonograph-path": "harmonographPath",
    "lighting.cluster-light-bins": "clusterLightBins",
}


def _module_path():
    lane = LANES.get("telos")
    if lane is None or not lane.source_repo:
        return None
    p = REPO.parent / lane.source_repo / "demo" / "creative-kernels.mjs"
    return p if p.exists() else None


def run_kernel(kernel: str, args: "dict | None" = None,
               timeout: float = 30.0) -> dict:
    """Run one bridged kernel with JSON args; the answer is the kernel's."""
    fn = KERNELS.get(kernel)
    if fn is None:
        return {"error": f"unknown kernel {kernel!r}; bridged: "
                         f"{', '.join(sorted(KERNELS))}"}
    mod = _module_path()
    if mod is None:
        return {"error": "the telos source checkout is absent; the kernel "
                         "cannot run without the lane"}
    shim = (
        f"import {{ {fn} }} from {json.dumps(mod.resolve().as_uri())};\n"
        "const args = JSON.parse(process.argv[1] || '{}');\n"
        f"process.stdout.write(JSON.stringify({fn}(args)));\n")
    try:
        r = subprocess.run(
            ["node", "--input-type=module", "-e", shim,
             json.dumps(args or {})],
            capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return {"error": "node is not on PATH; the telos kernels run in node"}
    except subprocess.TimeoutExpired:
        return {"error": f"kernel timed out after {timeout}s"}
    if r.returncode != 0:
        return {"error": "kernel failed: "
                         + (r.stderr or "").strip()[:300]}
    try:
        out = json.loads(r.stdout)
    except ValueError:
        return {"error": "kernel produced non-JSON output"}
    return {"schema": SCHEMA, "kernel": kernel, "lane": "telos",
            "module": "demo/creative-kernels.mjs", "result": out}
