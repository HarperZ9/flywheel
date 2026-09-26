"""wrapper_turn_receipt_hook.py -- deprecated; runs the capture hook module.

This script used to POST the turn to /api/scaffold with no token, and the
gateway refused it with a 401 the script hid. It now prints one deprecation
line on stderr and runs `python -m harness.capture_hooks stop --client
claude-code`, which authenticates, fails visibly and spools what it could not
send. Mount the module directly; `flywheel traces hooks print-mount` prints
the line. This wrapper stays for one release.
"""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from harness.capture_hooks.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.stderr.write("flywheel capture: wrapper_turn_receipt_hook.py is deprecated; "
                     "mount python -m harness.capture_hooks stop instead\n")
    raise SystemExit(main(["stop", "--client", "claude-code", *sys.argv[1:]]))
