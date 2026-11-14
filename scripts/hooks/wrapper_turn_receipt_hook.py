"""wrapper_turn_receipt_hook.py -- removed in Flywheel 2.0; this file only says so.

In 1.x this script forwarded to `python -m harness.capture_hooks stop`
and printed a deprecation line. In 2.0 it forwards nothing: it writes one
line naming the replacement and exits 1, so a mount that still points here
fails where the user can see it and captures nothing. Mount the module
directly; `flywheel traces hooks print-mount` prints the line, and
docs/MIGRATING-2.0.md has the steps.
"""
from __future__ import annotations

import sys

MESSAGE = ("flywheel capture: wrapper_turn_receipt_hook.py was removed in Flywheel 2.0 and "
           "captured nothing; mount python -m harness.capture_hooks stop "
           "instead (flywheel traces hooks print-mount prints the line; see "
           "docs/MIGRATING-2.0.md)\n")

if __name__ == "__main__":
    sys.stderr.write(MESSAGE)
    raise SystemExit(1)
