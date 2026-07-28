"""PyInstaller entry for the frozen Flywheel gateway.

The desktop app launches this exe by absolute path (its `engine/` folder), so
a clean machine needs no Python and no `flywheel` on PATH. Everything else --
routes, receipts, the plugins registry, static shell -- is the same code the
pip install runs; the freeze changes distribution, not behavior. Lane servers
stay separate installs: a frozen gateway launches them by console script only
(harness.lanes._frozen) and reports their honest health."""
import multiprocessing
import sys

from harness.gateway import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
