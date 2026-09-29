"""``flywheel install``: strict arguments, then pip/npm for the named lanes.

Nothing installs until every argument parses. ``-h`` or ``--help`` prints the
usage and exits 0. An unknown argument, a flag without its value, a flag given
twice, an unknown profile or an empty lane list prints the error and the usage
on stderr and exits 2. Each flag takes ``--flag value`` or ``--flag=value``.
"""
from __future__ import annotations

import sys

USAGE = ("usage: flywheel install [--lanes all|NAME[,NAME...]] [--profile package|source]\n"
         "  --lanes    the lanes to install (default: all)\n"
         "  --profile  package installs the pinned release; source installs a local "
         "checkout (default: package)")
PROFILES = ("package", "source")
_FLAGS = ("--lanes", "--profile")


class LaneArgsError(ValueError):
    """The arguments do not parse; the message says which one and why."""


class LaneArgsHelp(Exception):
    """The caller asked for the usage."""


def _value(argv: list[str], i: int) -> tuple[str, str, int]:
    """(flag, value, next index) for the flag at ``argv[i]``."""
    flag, eq, value = argv[i].partition("=")
    if flag not in _FLAGS:
        raise LaneArgsError(f"unknown argument: {argv[i]}")
    if not eq:
        if i + 1 >= len(argv) or argv[i + 1].startswith("-"):
            raise LaneArgsError(f"{flag} needs a value")
        return flag, argv[i + 1], i + 2
    return flag, value, i + 1


def parse_lane_args(argv: list[str]) -> tuple[str, str]:
    """(lanes, profile) from ``argv``; defaults all lanes, package profile.

    Raises LaneArgsHelp for -h/--help and LaneArgsError for anything else that
    does not parse.
    """
    if any(arg in ("-h", "--help") for arg in argv):
        raise LaneArgsHelp()
    found: dict[str, str] = {}
    i = 0
    while i < len(argv):
        flag, value, i = _value(argv, i)
        if flag in found:
            raise LaneArgsError(f"{flag} was given twice")
        if not value.strip():
            raise LaneArgsError(f"{flag} needs a value")
        found[flag] = value.strip()
    lanes = found.get("--lanes", "all")
    profile = found.get("--profile", "package")
    if profile not in PROFILES:
        raise LaneArgsError(f"--profile must be one of {', '.join(PROFILES)}, not {profile}")
    if lanes != "all" and not [n for n in lanes.split(",") if n.strip()]:
        raise LaneArgsError("--lanes names no lane")
    return lanes, profile


def _usage_error(message: str) -> int:
    print(f"flywheel install: {message}", file=sys.stderr)
    print(USAGE, file=sys.stderr)
    return 2


def cmd_install(argv: list[str]) -> int:
    """`flywheel install [--lanes all|index,gather,...] [--profile source|package]`.

    Pip/npm install the flagship lanes and record the result in the lane
    registry (~/.flywheel/lanes.json). Idempotent: re-runs upgrade a lane."""
    try:
        lanes_arg, profile = parse_lane_args(list(argv))
    except LaneArgsHelp:
        print(USAGE)
        return 0
    except LaneArgsError as error:
        return _usage_error(str(error))
    from harness.lanes import LANES, LANE_REGISTRY_PATH, install_lane, read_registry, write_registry
    if lanes_arg == "all":
        names = [n for n, lane in LANES.items() if lane.kind not in ("bundled", "http")]
    else:
        names = [n.strip() for n in lanes_arg.split(",") if n.strip()]
        bad = [n for n in names if n not in LANES]
        if bad:
            return _usage_error(f"unknown lane(s): {bad}; known: {list(LANES)}")
    print(f"Flywheel install -- {len(names)} lane(s), profile={profile}")
    registry = read_registry()
    n_ok = 0
    for name in names:
        lane = LANES[name]
        print(f"  installing {name} ({lane.kind}: {lane.install_name}) ...", end=" ", flush=True)
        result = install_lane(name, profile=profile)
        ok = result["installed"]
        print("OK" if ok else "FAILED")
        if not ok:
            print(f"    {result.get('detail', '')[:200]}", file=sys.stderr)
        kept = registry.get(name) if isinstance(registry.get(name), dict) else {}  # keeps env_allow
        registry[name] = {**kept, "install_name": lane.install_name, "kind": lane.kind,
                          "profile": profile, "installed": ok, "version": lane.version}
        n_ok += ok
    write_registry(registry)
    print(f"\n{n_ok}/{len(names)} lanes installed. Registry: {LANE_REGISTRY_PATH}")
    return 0 if n_ok == len(names) else 1
