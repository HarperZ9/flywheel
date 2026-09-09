"""Compatibility module for `python -m harness.writing_lint.check_writing`."""
from __future__ import annotations

from .check import *

if __name__ == "__main__":
    raise SystemExit(main())
