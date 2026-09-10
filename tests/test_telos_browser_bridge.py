"""Run only the synthetic Node protocol module, never native browser probes."""
import importlib.resources
from pathlib import Path
import shutil
import subprocess
import tomllib

import pytest


def test_bridge_is_an_exact_package_resource():
    root = Path(__file__).parents[1]
    settings = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert "telos_browser_bridge.mjs" in settings["tool"]["setuptools"]["package-data"]["harness"]
    resource = importlib.resources.files("harness").joinpath("telos_browser_bridge.mjs")
    assert resource.is_file()


def test_synthetic_node_bridge_controls():
    node = shutil.which("node")
    if node is None:
        pytest.skip("optional Node runtime is unavailable; no bridge-runtime coverage")
    result = subprocess.run([node, "--test", str(Path(__file__).with_name("telos_browser_bridge.test.mjs"))],
        capture_output=True, text=True, timeout=15,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert result.returncode == 0, result.stdout + result.stderr
