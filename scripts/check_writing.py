#!/usr/bin/env python3
"""Compatibility shim for `harness.writing_lint.check`."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from harness.writing_lint import check as _impl

for _name, _value in vars(_impl).items():
    if _name not in {"__name__", "__package__", "__loader__", "__spec__", "__builtins__"}:
        globals()[_name] = _value

if __name__ == "__main__":
    raise SystemExit(main())
