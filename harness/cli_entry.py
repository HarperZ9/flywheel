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
_UMBRELLA_COMMANDS = {"lanes", "loop-status", "install", "up", "down", "corpus-export",
                      "gate", "why", "auth"}


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
    """Locate the flywheel checkout containing scripts/ and harness/."""
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


def _launch_gateway(gateway_argv: list[str]) -> int:
    """Start the gateway. Prefer a source checkout (dev: run_harness_cli.py wires
    up cwd-relative dispatch and serves site/); otherwise -- a frozen exe or a
    bare `pip install`, neither of which ships scripts/ -- run the gateway
    straight from the installed harness package."""
    repo_root = None
    if not getattr(sys, "frozen", False):
        try:
            repo_root = find_repo_root()
        except FileNotFoundError:
            repo_root = None
    if repo_root is None:
        from harness.gateway import main as _gw_main
        return _gw_main(gateway_argv)
    os.chdir(repo_root)
    script = repo_root / "scripts" / "run_harness_cli.py"
    sys.argv = [str(script), "app", *gateway_argv]
    try:
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit as exc:
        return int(exc.code or 0)
    return 0


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
    return _launch_gateway(gateway_argv)


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
        roster = lane_roster(probe="--probe" in argv)
        print(lane_report(roster))
        return 0
    if command == "auth":
        from harness.oauth_signin import cli as _auth_cli
        return _auth_cli(argv)
    if command == "why":
        # Asking must be the cheapest action available: a path, optionally a
        # claim-digest prefix, no flags, no network, no model.
        from harness.why import explain, render, WhyError
        args = [a for a in argv if not a.startswith("-")]
        if not args:
            print("usage: flywheel why <receipt.json | dir> [claim-digest-prefix]",
                  file=sys.stderr)
            return 2
        try:
            report = explain(Path(args[0]), prefix=args[1] if len(args) > 1 else "")
        except WhyError as e:
            print(f"cannot answer from the record: {e}", file=sys.stderr)
            return 1
        print(render(report))
        return 0
    if command == "gate":
        # The Phase 0 disproof gate: oracle -> group -> receipt -> re-witness,
        # end to end, with no model and no candidate code executed. Exit 0 only
        # on MATCH.
        from harness.gate import run_gate
        out = Path(argv[0]) if argv and not argv[0].startswith("-") else (
            find_repo_root() / "artifacts" / "gate")
        report = run_gate(out)
        for s in report.steps:
            detail = ", ".join(f"{k}={v}" for k, v in s.items() if k != "step")
            print(f"  {s['step']}: {detail}")
        print(f"verdict={report.verdict} rewitness={report.rewitness}")
        print(f"subject={report.envelope_hash} claim={report.claim_hash} "
              f"signal={report.group_signal_hash}")
        return 0 if report.rewitness == "MATCH" else 1
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
    # `app` launches the gateway; route it through the shared launcher so it
    # works from a source checkout, a frozen exe, or a bare `pip install`.
    # Drop only the command token itself: an equality filter would also eat
    # a later value that happens to equal "app" (e.g. `--root app`).
    if command == "app":
        gw_args = list(raw)
        gw_args.remove("app")
        return _launch_gateway(gw_args)
    # Other passthrough commands re-invoke scripts/run_harness_cli.py from the
    # repo root (its cwd-relative subprocess dispatch needs the checkout). With
    # no checkout -- a frozen exe or a bare `pip install`, neither of which ships
    # scripts/ -- report that instead of raising.
    repo_root = None
    if not getattr(sys, "frozen", False):
        try:
            repo_root = find_repo_root()
        except FileNotFoundError:
            repo_root = None
    if repo_root is None:
        if command is None:
            # Bare `flywheel` or `flywheel --help` with no checkout: show the
            # umbrella usage. Help is a success; a missing command is an error.
            wants_help = any(a in ("-h", "--help") for a in raw)
            print("usage: flywheel <command> [options]\n"
                  "Umbrella commands (run from a bare install): up, lanes, "
                  "loop-status, install, corpus-export, gate, why, down\n"
                  "Passthrough commands need a source checkout "
                  "(scripts/run_harness_cli.py).",
                  file=sys.stdout if wants_help else sys.stderr)
            return 0 if wants_help else 2
        print(f"`flywheel {command}` requires a source checkout (scripts/run_harness_cli.py).",
              file=sys.stderr)
        print("Run from a checkout, or use the umbrella commands "
              "(up, lanes, loop-status, install, corpus-export).", file=sys.stderr)
        return 2
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
