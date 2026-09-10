"""PyInstaller entry for the frozen Flywheel gateway.

The desktop app launches this exe by absolute path (its `engine/` folder), so
a clean machine needs no Python and no `flywheel` on PATH. Everything else --
routes, receipts, the plugins registry, static shell -- is the same code the
pip install runs; the freeze changes distribution, not behavior. The Relay
status probe is a fixed self-child mode so the gateway never consults PATH or a
collided package name for the first bundled Relay admission."""
import multiprocessing
import sys


def main(argv=None) -> int:
    multiprocessing.freeze_support()
    from harness.bundled_lane_admission import dispatch_bundled_lane_mcp
    bundled = dispatch_bundled_lane_mcp(sys.argv[1:] if argv is None else argv)
    if bundled is not None:
        return bundled
    from harness.gateway import main as gateway_main
    return gateway_main(argv)


if __name__ == "__main__":
    sys.exit(main())
