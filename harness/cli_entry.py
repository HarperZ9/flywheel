"""cli_entry.py — the ``flywheel`` command dispatcher.

Single console-script entry (``flywheel = harness.cli_entry:main``). Thin
layer over run_harness_cli.py plus umbrella commands that work without a
checkout (frozen exe, bare pip install, or relay submodule).
"""
from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path
from harness.cli_version import print_version_if_asked
# The new umbrella subcommands. Handled in cli_entry; everything else is
# delegated to the existing run_harness_cli front controller.
_UMBRELLA_COMMANDS = {"lanes", "loop-status", "install", "up", "down", "corpus-export",
                      "gate", "why", "auth", "remote", "relay"}
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
# `flywheel install` parses strictly and lives in its own module; the names
# stay here because callers and tests reach them through cli_entry.
from harness.lane_install_cli import cmd_install as _cmd_install  # noqa: E402
from harness.lane_install_cli import parse_lane_args as _parse_lane_args  # noqa: E402,F401


def _launch_gateway(gateway_argv: list[str]) -> int:
    """Serve in this process, retaining a source checkout's working directory."""
    repo_root = None
    if not getattr(sys, "frozen", False):
        try:
            repo_root = find_repo_root()
        except FileNotFoundError:
            repo_root = None
    if repo_root is not None:
        os.chdir(repo_root)
        # Prefix the selected root so explicit caller options still win. The
        # imported package can live elsewhere; its REPO default is not this cwd.
        gateway_argv = ["--root", str(repo_root), *gateway_argv]
    # The generic script dispatcher spawns another Python process. A desktop
    # owner stopping its launcher must not leave that gateway running behind it.
    # Use the gateway's portable, configured run-root default in every mode.
    from harness.gateway import main as _gw_main
    return _gw_main(gateway_argv)


def _cmd_up(argv: list[str]) -> int:
    """`flywheel up [--port 8799] [--probe]` — preflight lane roster then gateway."""
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
        from harness.gate import run_gate, gate_output_directory
        out = gate_output_directory(argv, find_repo_root)
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
        print("`flywheel down` stops a gateway started by `flywheel up`.\n"
              "On Windows, close the gateway process (Ctrl-C in its console).",
              file=sys.stderr)
        return 0
    if command == "corpus-export":
        import json as _json
        from harness.corpus_export import export_corpus
        args = [a for a in argv if not a.startswith("-")]
        if len(args) < 2:
            print("usage: flywheel corpus-export <envelopes_dir> <out.jsonl> "
                  "[verdict_filter]", file=sys.stderr)
            return 2
        r = export_corpus(args[0], args[1],
                          verdict_filter=args[2] if len(args) > 2 else "PASS")
        print(_json.dumps(r, indent=2))
        return 0
    if command == "remote":
        from harness.relay_bridge import cmd_remote
        return cmd_remote(argv)
    if command == "relay":
        from harness.relay_bridge import cmd_relay
        return cmd_relay(argv)
    return 2
# Commands that live in the package and run without a source checkout.
_PACKAGED = {"acp": "harness.acp_cli", "dap": "harness.dap_cli",
             "lsp": "harness.lsp_cli", "packs": "harness.packs_cli",
             "evidence": "harness.evidence_cli", "import-norvane": "harness.norvane_capture_cli",
             "bulletin-identity": "harness.bulletin_identity_cli",
             "check-output": "harness.output_check_cli",
             "import-inspect": "harness.inspect_evidence_cli",
             "incident-sim": "harness.incident_sim_cli",
             "cross-harness-execute": "harness.cross_harness_cli",
             "workstream": "harness.workstream_cli",
             "journey": "harness.journey_cli", "grant": "harness.journey_cli",
             "e2e-journey": "harness.e2e_cli", "endpoint-gate": "harness.model_endpoint_gate_cli", "writing": "harness.writing_cli",
             "gov": "harness.governance_cli", "traces": "harness.trace_cli",
             "monitor": "harness.preaction.cli", "rederive": "harness.rederive_gate",
             "verify-share": "harness.verification_share_cli",
             "anchor": "harness.anchor_cli"}
def _dispatch_packaged(command: str, raw: list[str]) -> int | None:
    module = _PACKAGED.get(command)
    if module is None:
        return None
    from importlib import import_module
    rest = list(raw); rest.remove(command)  # the token, not a later equal value
    # journey and grant are two commands of one parser, so it keeps the name.
    return import_module(module).main([command, *rest]
                                      if command in {"journey", "grant"} else rest)
def main(argv: list[str] | None = None) -> int:
    raw = list(argv if argv is not None else sys.argv[1:])
    # The first non-flag token is the command: run_harness_cli requires a
    # subcommand, so it decides umbrella versus passthrough.
    command = next((a for a in raw if not a.startswith("-")), None)
    if command is None and print_version_if_asked(raw): return 0  # --version, -V
    packaged = _dispatch_packaged(command, raw)
    if packaged is not None:
        return packaged
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
                  "loop-status, install, corpus-export, gate, why, down, "
                  "remote, relay, grant, journey, evidence, bulletin-identity,\n"
                  "cross-harness-execute, check-output, packs, workstream, "
                  "endpoint-gate, writing, import-inspect, incident-sim, traces\n"
                  "Passthrough commands need a source checkout "
                  "(scripts/run_harness_cli.py).",
                  file=sys.stdout if wants_help else sys.stderr)
            return 0 if wants_help else 2
        print(f"`flywheel {command}` requires a source checkout (scripts/run_harness_cli.py).",
              file=sys.stderr)
        print("Run from a checkout, or use the umbrella commands "
              "(up, lanes, loop-status, install, corpus-export, endpoint-gate, writing).", file=sys.stderr)
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
