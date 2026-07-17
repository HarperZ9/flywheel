"""cli_entry.py -- the `flywheel` command dispatcher.

Flywheel is the one platform: routing + verification + the lane layer + the
closed verified-inference loop. This module is the single console-script entry
(``flywheel = harness.cli_entry:main`` in pyproject.toml).

Design: it is a thin layer over the existing ``scripts/run_harness_cli.py``
front controller. Every existing subcommand (app, manifest, registry,
benchmarks, mcp-health, ...) passes through unchanged. The new umbrella
subcommands -- ``lanes``, ``loop-status``, ``install``, ``up`` -- are handled
here once their modules land (Phase 2: lanes.py; Phase 3: loop-closure
updates). Until then they report a clear "not yet implemented" rather than
silently falling through.

Repo-root resolution mirrors ``scripts/local_harness_entry.py`` so the command
works identically as a console-script, from a checkout, and from a frozen exe.
"""
from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

# The new umbrella subcommands. Handled in cli_entry; everything else is
# delegated to the existing run_harness_cli front controller.
_UMBRELLA_COMMANDS = {"lanes", "loop-status", "install", "up", "down", "corpus-export"}


def _candidate_roots() -> list[Path]:
    candidates: list[Path] = []
    explicit = os.environ.get("FLYWHEEL_REPO", "").strip() or os.environ.get("LOCAL_HARNESS_REPO", "").strip()
    if explicit:
        candidates.append(Path(explicit))
    candidates.append(Path.cwd())
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        candidates.extend([exe.parent, exe.parent.parent, exe.parent.parent.parent])
    candidates.append(Path(__file__).resolve().parent.parent)
    return candidates


def find_repo_root() -> Path:
    """Locate the flywheel/local-model checkout containing scripts/ and harness/."""
    seen: set[Path] = set()
    for candidate in _candidate_roots():
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:
            continue
        for root in [resolved, *resolved.parents]:
            if root in seen:
                continue
            seen.add(root)
            if (root / "scripts" / "run_harness_cli.py").exists() and (root / "harness").is_dir():
                return root
    raise FileNotFoundError(
        "could not locate the flywheel repo root; set FLYWHEEL_REPO to the "
        "checkout containing scripts/run_harness_cli.py and harness/"
    )


def _parse_lane_args(argv: list[str]) -> tuple[str, str]:
    """Parse --lanes <list|all> and --profile <source|package> from argv.
    Defaults: all lanes, package profile."""
    lanes = "all"
    profile = "package"
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--lanes",) and i + 1 < len(argv):
            lanes = argv[i + 1]; i += 2; continue
        if a in ("--profile",) and i + 1 < len(argv):
            profile = argv[i + 1]; i += 2; continue
        i += 1
    return lanes, profile


def _cmd_install(argv: list[str]) -> int:
    """`flywheel install [--lanes all|index,gather,...] [--profile source|package]`.

    Pip/npm install the flagship lanes and record the result in the lane
    registry (~/.flywheel/lanes.json). Idempotent: re-runs upgrade a lane."""
    import json as _json
    from harness.lanes import LANES, install_lane, write_registry, read_registry, LANE_REGISTRY_PATH
    lanes_arg, profile = _parse_lane_args(argv)
    if lanes_arg == "all":
        names = [n for n, l in LANES.items() if l.kind != "bundled"]
    else:
        names = [n.strip() for n in lanes_arg.split(",") if n.strip()]
        bad = [n for n in names if n not in LANES]
        if bad:
            print(f"unknown lane(s): {bad}; known: {list(LANES)}", file=sys.stderr)
            return 2
    print(f"Flywheel install -- {len(names)} lane(s), profile={profile}")
    registry = read_registry()
    n_ok = 0
    for name in names:
        lane = LANES[name]
        print(f"  installing {name} ({lane.kind}: {lane.install_name}) ...", end=" ", flush=True)
        r = install_lane(name, profile=profile)
        ok = r["installed"]
        print("OK" if ok else "FAILED")
        if not ok:
            det = r.get("detail", "")
            print(f"    {det[:200]}", file=sys.stderr)
        registry[name] = {"install_name": lane.install_name, "kind": lane.kind,
                          "profile": profile, "installed": ok,
                          "version": lane.version}
        if ok:
            n_ok += 1
    write_registry(registry)
    print(f"\n{n_ok}/{len(names)} lanes installed. Registry: {LANE_REGISTRY_PATH}")
    return 0 if n_ok == len(names) else 1


def _cmd_up(argv: list[str]) -> int:
    """`flywheel up [--port 8799] [--probe]` -- start the one surface.

    Preflight: print the lane roster so the operator sees what is live before
    the gateway starts. Then delegate to the existing `app` subcommand (which
    launches harness/gateway.py). The gateway serves /api/lanes, /api/world,
    and the shell on one origin."""
    import sys as _sys
    # Preflight lane roster (fast, install-presence only, unless --probe).
    probe = "--probe" in argv
    from harness.lanes import lane_roster, lane_report
    print(lane_report(lane_roster(probe=probe)))
    print()
    # Strip our flags and delegate to `app` (the gateway launcher).
    gateway_argv = [a for a in argv if a not in ("--probe",)]
    if not any(a == "--port" for a in gateway_argv):
        gateway_argv = ["--port", "8799"] + gateway_argv
    print("Starting the gateway ...")
    _sys.stdout.flush()
    # Re-invoke run_harness_cli.py with `app` + our port/flags.
    repo_root = find_repo_root()
    os.chdir(repo_root)
    import runpy
    script = repo_root / "scripts" / "run_harness_cli.py"
    _sys.argv = [str(script), "app", *gateway_argv]
    try:
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit as exc:
        return int(exc.code or 0)
    return 0


def _dispatch_umbrella(command: str, argv: list[str]) -> int:
    """Handle the new umbrella subcommands. Phase 2/3 implement these fully."""
    if command == "loop-status":
        from harness.loop_closure import measure_loop, loop_report
        import tempfile
        m = measure_loop(tempfile.mkdtemp())
        print(loop_report(m))
        print()
        for h in m["handoffs"]:
            mark = "CLOSED" if h["closed"] else "OPEN"
            print(f"  {h['frm']:>10} -> {h['to']:<10} [{mark}]  {h['carries']}")
            print(f"             {h['evidence']}")
        return 0
    if command == "lanes":
        from harness.lanes import lane_roster, lane_report
        roster = lane_roster()
        print(lane_report(roster))
        return 0
    if command == "install":
        return _cmd_install(argv)
    if command == "up":
        return _cmd_up(argv)
    if command == "down":
        print("`flywheel down` stops a gateway started by `flywheel up`.", file=sys.stderr)
        print("On Windows, close the gateway process (Ctrl-C in its console).", file=sys.stderr)
        return 0
    if command == "corpus-export":
        # Gap E: export verified envelopes to a training shard (operator-gated).
        import json as _json
        import sys as _sys
        from harness.corpus_export import export_corpus
        args = [a for a in argv if not a.startswith("-")]
        if len(args) < 2:
            print("usage: flywheel corpus-export <envelopes_dir> <out.jsonl> [verdict_filter]", file=_sys.stderr)
            return 2
        verdict = args[2] if len(args) > 2 else "PASS"
        r = export_corpus(args[0], args[1], verdict_filter=verdict)
        print(_json.dumps(r, indent=2))
        return 0
    return 2


def main(argv: list[str] | None = None) -> int:
    raw = list(argv if argv is not None else sys.argv[1:])
    # Peek at the first positional to decide umbrella-vs-passthrough. The
    # existing run_harness_cli parser requires a subcommand, so the first
    # non-flag token is the command name.
    command = next((a for a in raw if not a.startswith("-")), None)
    if command in _UMBRELLA_COMMANDS:
        rest = [a for a in raw if a is not command]
        return _dispatch_umbrella(command, rest)
    # Passthrough: re-invoke scripts/run_harness_cli.py from the repo root so
    # its cwd-relative subprocess dispatch (build_command) resolves correctly.
    # When frozen (PyInstaller exe), the scripts/ dir is not bundled; for the
    # `app` command we import harness.gateway directly, and for other commands
    # we report they need a source checkout.
    if getattr(sys, "frozen", False):
        if command == "app":
            # The gateway is importable from the bundled harness package.
            # Strip the "app" command name; gateway.main takes --port/--root/etc.
            from harness.gateway import main as _gw_main
            gw_args = [a for a in raw if a != "app"]
            return _gw_main(gw_args)
        print(f"`flywheel {command}` requires a source checkout (scripts/run_harness_cli.py).",
              file=sys.stderr)
        print("Run from a checkout, or use the umbrella commands "
              "(lanes, loop-status, install, up, corpus-export).", file=sys.stderr)
        return 2
    repo_root = find_repo_root()
    os.chdir(repo_root)
    script = repo_root / "scripts" / "run_harness_cli.py"
    sys.argv = [str(script), *raw]
    try:
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit as exc:
        return int(exc.code or 0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
