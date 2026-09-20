"""Check staged runtime imports without site-packages or developer search paths."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from typing import Iterable

_CHECK = """
import importlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1]).resolve()
sys.path[:0] = [str(root / 'studio_runtime_python'),
               str(root / 'harness/studio_engine_bundle')]
rows = []
for name in json.loads(sys.argv[2]):
    module = importlib.import_module(name)
    path = pathlib.Path(module.__file__).resolve()
    relative = path.relative_to(root).as_posix()
    rows.append({'module': name, 'path': relative})
print(json.dumps(rows))
"""


def verify_payload_imports(
    payload_root: Path | str, modules: Iterable[str],
) -> list[dict[str, str]]:
    """Require imports to resolve inside the payload, without writing bytecode."""
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-B", "-c", _CHECK,
         str(Path(payload_root).resolve()), json.dumps(sorted(set(modules)))],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode:
        raise RuntimeError("Studio runtime import closure failed: " + result.stderr.strip())
    return json.loads(result.stdout)
