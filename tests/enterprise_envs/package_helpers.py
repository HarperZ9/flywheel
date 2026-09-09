from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = ROOT / "packages" / "service-desk-incident-env"
PACKAGE_SRC = PACKAGE_ROOT / "src"


def add_product_src() -> None:
    text = str(PACKAGE_SRC)
    if text not in sys.path:
        sys.path.insert(0, text)


def product_pythonpath(*extra: Path) -> str:
    parts = [*(str(path) for path in extra), str(PACKAGE_SRC), str(ROOT)]
    current = os.environ.get("PYTHONPATH")
    if current:
        parts.append(current)
    return os.pathsep.join(parts)
