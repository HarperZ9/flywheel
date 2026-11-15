#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""cli.py - the unified `emet` entry point.

One command surface over the three Python-core tools, dispatching to each
module's existing main() by name (nothing about a verdict changes here):

  emet anchor|verify|coherence|refuse|corroborate|audit|selftest ...  -> membrane
  emet watch|observe|confirm|gate ...                                 -> organs
  emet monitor report|reanchor ...                                    -> monitor

A global --json flag is passed straight through to the underlying command
(membrane honours it per SPEC s.13; organs/monitor ignore it). The exit code and
every emitted byte are exactly those of the underlying tool - this is routing,
not a new surface.
"""
import sys
from . import membrane, organs, monitor

_MEMBRANE = ("anchor", "verify", "coherence", "refuse", "corroborate", "audit",
             "selftest", "receipt", "check", "rebind")
_ORGANS = ("watch", "observe", "confirm", "gate")

USAGE = (
    "usage: emet <command> [args...] [--json]\n"
    "  byte-hash core: anchor verify coherence refuse corroborate audit selftest\n"
    "  portable receipt: receipt --from-json <file|-> | check <receipt.json>\n"
    "  rebind (experimental): rebind <naked> --manifest <m.json> [--claim <id>]\n"
    "  perception/gate: watch observe confirm gate\n"
    "  monitor:         monitor report <manifest> | monitor reanchor <manifest>\n"
    "  --json emits a machine-readable canonical envelope (SPEC s.13)."
)

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    non_flags = [a for a in argv if not a.startswith("-")]
    cmd = non_flags[0] if non_flags else None
    if cmd in _MEMBRANE:
        sys.argv = ["emet", *argv]
        membrane.main()
    elif cmd in _ORGANS:
        sys.argv = ["emet", *argv]
        organs.main()
    elif cmd == "monitor":
        # Drop the "monitor" group token once; monitor.main() dispatches on report/reanchor.
        i = argv.index("monitor")
        sys.argv = ["emet", *argv[:i], *argv[i + 1:]]
        monitor.main()
    else:
        sys.stderr.write(USAGE + "\n")
        sys.exit(64)

if __name__ == "__main__":
    main()
