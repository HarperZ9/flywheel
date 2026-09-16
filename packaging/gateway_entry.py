"""PyInstaller entry for the frozen Flywheel gateway.

The desktop app launches this exe by absolute path (its `engine/` folder), so
a clean machine needs no Python and no `flywheel` on PATH. Everything else --
routes, receipts, the plugins registry, static shell -- is the same code the
pip install runs; the freeze changes distribution, not behavior. The Relay
status probe is a fixed self-child mode so the gateway never consults PATH or a
collided package name for the first bundled Relay admission."""
import multiprocessing
import sys

_MCP_VALUE_FLAGS = {"--root", "--run-root"}


def _valid_frozen_mcp_args(args: list[str]) -> bool:
    if not args or args[0] != "--mcp" or args.count("--mcp") != 1:
        return False
    seen: set[str] = set()
    i = 1
    while i < len(args):
        arg = args[i]
        if arg in _MCP_VALUE_FLAGS:
            if arg in seen or i + 1 >= len(args) or args[i + 1].startswith("--"):
                return False
            seen.add(arg)
            i += 2
            continue
        if any(arg.startswith(flag + "=") for flag in _MCP_VALUE_FLAGS):
            flag, value = arg.split("=", 1)
            if flag in seen or not value:
                return False
            seen.add(flag)
            i += 1
            continue
        return False
    return True


def _dispatch_frozen_mcp(argv: list[str]) -> int | None:
    if "--mcp" not in argv:
        return None
    if not _valid_frozen_mcp_args(argv):
        return 2
    from harness.local_agent_cli import main as local_agent_main
    return local_agent_main(argv)


def main(argv=None) -> int:
    multiprocessing.freeze_support()
    args = list(sys.argv[1:] if argv is None else argv)
    from harness.bundled_lane_admission import dispatch_bundled_lane_mcp
    bundled = dispatch_bundled_lane_mcp(args)
    if bundled is not None:
        return bundled
    frozen_mcp = _dispatch_frozen_mcp(args)
    if frozen_mcp is not None:
        return frozen_mcp
    from harness.gateway import main as gateway_main
    return gateway_main(args)


if __name__ == "__main__":
    sys.exit(main())
