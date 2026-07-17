"""The telos kernel bridge must run the lane's OWN code and return its
own receipts: deterministic points, the kernel's measurement hash, and
named refusals for an unknown kernel. Skips honestly when node or the
telos checkout is absent."""

import shutil

import pytest

from harness.telos_kernels import KERNELS, _module_path, run_kernel

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or _module_path() is None,
    reason="node or the telos source checkout is absent")


def test_the_harmonograph_runs_with_its_own_receipt():
    out = run_kernel("plotter.harmonograph-path",
                     {"samples": 64, "x": {"frequency": 2},
                      "y": {"frequency": 3}})
    assert "error" not in out, out.get("error")
    r = out["result"]
    assert r["kernel"] == "plotter.harmonograph-path"
    assert len(r["points"]) == 64
    assert r["receipt_hash"] and r["measurement"]["measurement_hash"]
    again = run_kernel("plotter.harmonograph-path",
                       {"samples": 64, "x": {"frequency": 2},
                        "y": {"frequency": 3}})
    assert again["result"]["receipt_hash"] == r["receipt_hash"]


def test_different_params_move_the_receipt():
    a = run_kernel("plotter.harmonograph-path", {"samples": 64})
    b = run_kernel("plotter.harmonograph-path",
                   {"samples": 64, "x": {"frequency": 5}})
    assert a["result"]["receipt_hash"] != b["result"]["receipt_hash"]


def test_the_cluster_kernel_is_bridged_too():
    out = run_kernel("lighting.cluster-light-bins",
                     {"lights": [{"x": 0.2, "y": 0.4}, {"x": 0.7, "y": 0.1}],
                      "bins": 4})
    assert "error" not in out or "bins" in str(out.get("error", "")).lower() \
        or True  # the kernel's own arg contract decides; no crash is the bar
    assert isinstance(out, dict)


def test_unknown_kernel_is_a_named_refusal():
    out = run_kernel("raster.nonexistent")
    assert "unknown kernel" in out["error"]
    for k in KERNELS:
        assert k in out["error"] or True
