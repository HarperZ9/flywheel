"""The capture hooks run from a client's interpreter, so importing them must
load nothing outside the standard library and the hook package itself."""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MODULES = ("harness.capture_hooks", "harness.capture_hooks.__main__",
           "harness.capture_hooks.client", "harness.capture_hooks.home",
           "harness.capture_hooks.listener_owner", "harness.capture_hooks.spool",
           "harness.capture_hooks.output", "harness.capture_hooks.protocol",
           "harness.capture_hooks.protect")
PROBE = """
import importlib, json, sys
before = set(sys.modules)
for name in {modules!r}:
    importlib.import_module(name)
print(json.dumps(sorted(set(sys.modules) - before)))
"""


def _loaded(modules=MODULES) -> list[str]:
    out = subprocess.run([sys.executable, "-s", "-c", PROBE.format(modules=modules)],
                         cwd=str(REPO), capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _outside(names) -> list[str]:
    stdlib = set(sys.stdlib_module_names)
    return [n for n in names if n.split(".")[0] not in stdlib
            and n != "harness" and not n.startswith("harness.capture_hooks")]


def test_importing_the_hook_package_loads_only_the_standard_library():
    assert _outside(_loaded()) == []


def test_control_a_module_outside_the_package_is_seen():
    """False-success control: the probe must notice a harness module."""
    assert "harness.evidence_json" in _outside(_loaded(("harness.evidence_json",)))
