"""cli_help.py -- what `flywheel --help` prints, and the answer to a command
that does not exist.

Every command the dispatcher accepts has one line here; a test fails when a
command is added to cli_entry without one. A mistyped command gets "not a
command" and the nearest real name. "Requires a source checkout" is kept for
the commands that do.
"""
from __future__ import annotations

import difflib

# Grouped for reading. Each entry: command -> one line.
GROUPS = (
    ("Start here", {
        "setup": "connect a model: store and test a provider key, by account",
        "auth": "accounts and sign-in: list, use, remove, status, login, logout",
        "doctor": "check that this install is ready to work",
        "code": "an interactive coding session in the current folder",
        "up": "start the local gateway on 127.0.0.1",
        "down": "say what is running and how to stop it",
        "gateway-key": "local keys with budgets for tools behind the gateway",
        "app": "start the gateway without the lane list (same server as `up`)",
        "update": "ask whether a newer Flywheel is out",
    }),
    ("Check and record", {
        "gate": "run one built-in task end to end with no model; exit 0 on MATCH",
        "why": "explain a receipt or a gate record from the file, offline",
        "check-output": "check an answer against the sources that decide it",
        "packs": "list the domain packs and what each one decides",
        "rederive": "accept a claimed improvement only if reruns reproduce it",
        "anchor": "have outside parties witness a head",
        "verify-share": "verified share over time and the cost to verify",
        "report": "report calls that reached past what was allowed",
        "behavior-check": "replay scripted sessions on two builds and compare",
        "corpus-export": "export sealed envelopes as a JSONL corpus",
    }),
    ("Extend the coding session", {
        "mcp": "list, add, remove and sign in to MCP servers",
        "plugin": "install, list and remove plugins",
        "acp": "delegate a turn to an Agent Client Protocol agent",
        "lsp": "ask a language server about a file",
        "dap": "debug a program under a debug adapter",
    }),
    ("Lanes and remote", {
        "lanes": "list every lane and whether it is installed",
        "install": "install lanes, for example `flywheel install --lanes relay`",
        "loop-status": "measure the closed loop's handoffs in a scratch folder",
        "relay": "the relay coding agent (needs the relay lane)",
        "remote": "remote access through relay (needs the relay lane)",
    }),
    ("Records, journeys and governance", {
        "traces": "where your traces are and what can be done with them",
        "monitor": "pre-action coverage, pending holds, approve and reject",
        "gov": "run the governance instruments",
        "journey": "durable journey actions, as JSON",
        "grant": "exact grant actions for a journey, as JSON",
        "evidence": "the unified evidence journey, as JSON",
        "e2e-journey": "product end-to-end journey manifests",
        "workstream": "settle a dependency graph of obligations",
        "writing": "the writing workspace workflow, as JSON",
        "endpoint-gate": "run bounded gates against local model endpoints",
        "cross-harness-execute": "run an admitted cross-harness execution",
        "import-inspect": "import Inspect JSON evidence locally",
        "import-norvane": "read one offline capture into a journey review",
        "incident-sim": "check a synthetic incident trace",
        "bulletin-identity": "prepare and bind a Bulletin signing identity",
    }),
)
COMMANDS = {name: line for _, group in GROUPS for name, line in group.items()}

# Commands that exist only in scripts/run_harness_cli.py, so they need a
# source checkout. A test compares this set with that script's parser.
CHECKOUT_ONLY = frozenset({
    "adapter-runtime", "agentic-tasks", "architecture-report", "benchmark-coverage",
    "benchmarks", "classifier-friction", "codex-mcp-contract", "comparison",
    "cross-harness", "embodied-realtime", "endpoint-launch-readiness",
    "enterprise-readiness", "execution-matrix", "forum-route", "manifest",
    "mcp-health", "model-card-claims", "model-publish", "null-floor", "outcome",
    "package-doctor", "plan", "query", "readiness", "registry", "runtime-contract",
    "schematic-drift", "seed", "serve-launch", "serve-resource", "session-summary",
    "task-set-executability", "tool-contract", "tool-hardening",
})


def usage() -> str:
    lines = ["usage: flywheel <command> [options]",
             "       flywheel <command> --help    for one command",
             "       flywheel --version"]
    for title, group in GROUPS:
        lines += ["", f"{title}:"]
        lines += [f"  {name:<22} {line}" for name, line in group.items()]
    lines += ["", "From a source checkout, the internal report commands in "
                  "scripts/run_harness_cli.py",
              "also run as `flywheel <name>`; list them with "
              "`python scripts/run_harness_cli.py --help`."]
    return "\n".join(lines)


def nearest(command: str) -> "str | None":
    known = sorted(set(COMMANDS) | CHECKOUT_ONLY)
    close = difflib.get_close_matches(command, known, n=1, cutoff=0.6)
    return close[0] if close else None


# Names people type from other tools, and the command that does that job here.
ALIASES = {"verify": "gate", "status": "doctor", "login": "auth", "logout": "auth",
           "accounts": "auth", "config": "setup", "init": "setup", "start": "up",
           "stop": "down", "chat": "code", "upgrade": "update"}


def unknown(command: str) -> str:
    """The message for a name that is not a command anywhere."""
    text = f"`flywheel {command}` is not a command."
    guess = ALIASES.get(command) or nearest(command)
    if guess:
        text += f" Did you mean `flywheel {guess}`?"
    return text + "\nRun `flywheel --help` for the list."


def needs_checkout(command: str) -> str:
    return (f"`flywheel {command}` requires a source checkout "
            "(scripts/run_harness_cli.py).\n"
            "Run it from a checkout, or see `flywheel --help` for the commands "
            "that work from an install (up, lanes, endpoint-gate, writing, ...).")


def down_report(environ) -> "tuple[int, str]":
    """What `flywheel down` can say. The gateway runs in the terminal that
    started it and offers no stop route, so this names it and how to end it."""
    from harness.capture_hooks.client import CaptureFailure, read_endpoint
    from harness.lane_workdir import flywheel_home
    how = ("`flywheel down` cannot stop it from here: the gateway has no stop "
           "route. Press Ctrl-C in the terminal that ran `flywheel up`, or close "
           "that window.")
    try:
        doc = read_endpoint(flywheel_home(environ))
    except CaptureFailure:
        return 0, ("No gateway is recorded as running under this Flywheel home, "
                   "so there is nothing to stop.")
    return 1, (f"A gateway is running at http://{doc['host']}:{doc['port']} "
               f"(process {doc['pid']}).\n{how}")
