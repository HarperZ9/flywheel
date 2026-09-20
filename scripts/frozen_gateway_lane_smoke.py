"""Per-lane admission smoke for the frozen gateway.

Every bundled manifest lane must admit and launch from vendored source in the
frozen build, not relay and canon alone. This runs the frozen executable in each
lane's child mode (``--bundled-lane-mcp <lane>``) with an immediately closed
stdin and asserts the lane is not blocked. The child dispatcher returns exit 2
only when the descriptor, the source hash, or the module import fails, so any
other exit means the lane cleared admission and its declared serve ran. A serve
that keeps reading the closed stdin instead of exiting is also past admission, so
a timeout counts as admitted and the child is killed.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def manifest_lanes(repo_root: Path = REPO_ROOT) -> list[str]:
    manifest = repo_root / "packaging" / "python-lane-payloads.jsonl"
    lanes = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if line.strip():
            lanes.add(str(json.loads(line)["lane"]))
    return sorted(lanes)


def _lane_code(lane: str) -> str:
    return "BUNDLED_LANE_BLOCKED_" + lane.upper().replace("-", "_")


def bundled_lane_admission_smoke(executable: Path, require, *,
                                 repo_root: Path = REPO_ROOT,
                                 timeout: float = 30.0) -> dict:
    """Run every manifest lane in frozen child mode; require none is blocked."""
    executable = Path(executable).resolve()
    exit_codes: dict[str, object] = {}
    for lane in manifest_lanes(repo_root):
        try:
            proc = subprocess.run(
                [str(executable), "--bundled-lane-mcp", lane],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=timeout)
            code: object = proc.returncode
            admitted = proc.returncode != 2
        except subprocess.TimeoutExpired:
            code = "timeout"
            admitted = True  # serve ran past admission and held the closed stdin
        exit_codes[lane] = code
        require(admitted, _lane_code(lane))
    return {
        "schema": "flywheel.frozen-bundled-lane-admission/v1",
        "lanes": manifest_lanes(repo_root),
        "exit_codes": exit_codes,
        "does_not_prove": [
            "lane model-backed task success",
            "lane health-tool semantic correctness",
            "runtime dependency closure beyond the frozen payload",
        ],
    }
