from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def pytest_configure() -> None:
    existing = os.environ.get("PYTHONPATH")
    os.environ["PYTHONPATH"] = str(SRC) if not existing else f"{SRC}{os.pathsep}{existing}"
