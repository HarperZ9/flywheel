#!/usr/bin/env python3
"""ci_lane_pins.py -- print the pip requirement for a lane at its registry pin.

The whole-suite CI job installs index-graph because the suite imports
index_graph and launches the index lane's MCP server. ci.yml used to name the
version by hand, a second copy of the pin in harness/lanes_registry.py. The
registry moved to 2.13.0 while ci.yml stayed on 2.10.0, and once an
auto-profile package older than its pin stopped launching, every test that
launches the index lane failed on the runner. This script reads the one copy.

    python scripts/ci_lane_pins.py index      ->  index-graph==2.14.0

Stdlib only, so it runs before pip has installed anything.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.lanes_registry import LANES  # noqa: E402


def requirement(name: str) -> str:
    """``<distribution>==<pin>`` for one pip lane of the registry."""
    lane = LANES[name]
    if lane.kind != "pip":
        raise ValueError(f"{name} is not a pip lane (kind {lane.kind}); pip cannot install it")
    return f"{lane.install_name}=={lane.version}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print pip requirements at lane pins.")
    parser.add_argument("lanes", nargs="+", help="lane names from harness/lanes_registry.py")
    args = parser.parse_args(argv)
    try:
        print(" ".join(requirement(name) for name in args.lanes))
    except KeyError as exc:
        print(f"ci_lane_pins: no lane named {exc.args[0]!r}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"ci_lane_pins: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
