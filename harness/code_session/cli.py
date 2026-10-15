"""`flywheel code`: an interactive coding session in the current folder.

  flywheel code                      start a session here
  flywheel code -p "fix the test"    run one request and exit
  flywheel code --mode edit          writes run without asking; commands still ask

Every turn runs the gated tool loop and lands on one hash-chained ledger.
Type /help inside the session for the commands.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import slash
from .backends import DEFAULT_MAX_TOKENS, build_agent, describe, ladder
from .policy import MODES, deny_all
from .session import DEFAULT_MAX_STEPS, new_session

NO_BACKEND = ("No model is reachable. Set a provider key (for example "
              "ANTHROPIC_API_KEY or OPENAI_API_KEY), start a local server such as "
              "ollama, or put the claude or codex CLI on PATH. `flywheel doctor` "
              "shows what is set.")


def parse_args(argv):
    ap = argparse.ArgumentParser(prog="flywheel code", description=__doc__.splitlines()[0])
    ap.add_argument("-p", "--print", dest="prompt", default=None, metavar="REQUEST",
                    help="run one request, print the answer and exit; with no one to ask, "
                         "calls that would ask are refused, so pass --mode edit or auto")
    ap.add_argument("--root", default=".", help="project folder (default: current folder)")
    ap.add_argument("--mode", choices=MODES, default="ask",
                    help="permission mode (default: ask)")
    ap.add_argument("--backend", default="auto", help="pin a backend by name")
    ap.add_argument("--model", default="", help="model id for the chosen backend")
    ap.add_argument("--providers", default="",
                    help="comma list of hosted providers to consider (default: all with keys)")
    ap.add_argument("--local-only", action="store_true", help="never call a hosted provider")
    ap.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS)
    ap.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    ap.add_argument("--test-cmd", default="", help="tests a turn must pass before it is done")
    ap.add_argument("--no-instructions", action="store_true",
                    help="do not read AGENTS.md, CLAUDE.md or FLYWHEEL.md")
    return ap.parse_args(argv)


def _home() -> str:
    from harness.lane_workdir import flywheel_home
    return str(flywheel_home(os.environ))


def prompt_approver(name: str, args: dict) -> str:
    """Ask the person at the keyboard. End of input is a no."""
    shown = json.dumps(args, ensure_ascii=False)
    shown = shown if len(shown) <= 300 else shown[:300] + " ..."
    while True:
        try:
            raw = input(f"  allow {name} {shown}? [y]es [n]o [a]lways: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return "no"
        if raw in ("y", "yes"):
            return "yes"
        if raw in ("a", "always"):
            return "always"
        if raw in ("n", "no", ""):
            return "no"


def print_event(event: dict) -> None:
    kind = event.get("type")
    if kind == "tool_call":
        args = json.dumps(event.get("args", {}), ensure_ascii=False)
        print(f"  > {event.get('name')} {args[:160]}", file=sys.stderr)
    elif kind == "tool_result":
        first = (event.get("output") or "").strip().splitlines()[:1]
        mark = "ok" if event.get("ok") else "FAIL"
        print(f"    {mark} {first[0][:160] if first else ''}", file=sys.stderr)


# The sandbox leaves the project folder read-only to commands: files change
# only through the gated, receipted write tools. Tools that cache inside the
# tree must be told so, or they fail (or, for pytest's cache, stall until the
# timeout). TEMP and HOME point at the run's own scratch folder.
SANDBOX_ENV = {"PYTHONDONTWRITEBYTECODE": "1", "PYTEST_ADDOPTS": "-p no:cacheprovider"}


def _runner():
    """Commands run in the OS sandbox with a writable scratch TEMP and HOME.

    A host with no sandbox refuses, unless FLYWHEEL_ALLOW_UNSANDBOXED=1 (or the
    machine policy) says to run bare and label the output."""
    from harness.sandboxed_runner import SandboxUnavailable, sandboxed_run
    from harness.tool_sandbox_bridge import fallback_from_env, make_unsandboxed_runner
    fallback = fallback_from_env()

    def run(cmd: str, root: str):
        try:
            return sandboxed_run(cmd, root, scratch_home=True, extra_env=SANDBOX_ENV)
        except SandboxUnavailable as e:
            if fallback != "disclose":
                return False, (f"[refused] no OS sandbox on this host ({e}). Set "
                               "FLYWHEEL_ALLOW_UNSANDBOXED=1 to run commands bare.")
            ok, out = make_unsandboxed_runner()(cmd, root)
            return ok, "[UNVERIFIABLE: sandbox unavailable] " + out
    return run


def build_session(args, *, backends=None, approver=None, runner=None, on_event=None):
    if backends is None:
        providers = [p.strip() for p in args.providers.split(",") if p.strip()] or None
        backends = ladder(providers=providers, online=not args.local_only, model=args.model)
    agent = build_agent(backends, prefer=args.backend, max_tokens=args.max_tokens)
    root = os.path.abspath(args.root)
    session = new_session(agent, root, mode=args.mode, approver=approver,
                          runner=runner if runner is not None else _runner(),
                          max_steps=args.max_steps, test_cmd=args.test_cmd or None,
                          on_event=on_event)
    if not args.no_instructions:
        session.load_instructions(_home())
    return session


def _footer(result) -> str:
    tests = "" if result.tests_pass is None else f" | tests_pass={result.tests_pass}"
    return (f"[{result.steps} step(s) | {result.seconds:.1f}s | chain "
            f"{'ok' if result.verified else 'BROKEN'}{tests} | ledger {result.checkpoint[:12]}]")


def run_turn(session, text: str) -> int:
    from harness.local_agent import BackendError
    try:
        result = session.turn(text)
    except BackendError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 1
    print(result.final)
    print(_footer(result), file=sys.stderr)
    return 1 if result.tests_pass is False else 0


def _read_request() -> "str | None":
    """One request; a trailing backslash continues it on the next line."""
    lines = []
    while True:
        line = input("flywheel> " if not lines else "      ... ")
        if line.endswith("\\"):
            lines.append(line[:-1])
            continue
        lines.append(line)
        return "\n".join(lines).strip()


def repl(session) -> int:
    print(f"Flywheel code | {session.root} | mode {session.executor.mode} | "
          f"{describe(session.agent.live_backend())}", file=sys.stderr)
    if session.loaded:
        print("instructions: " + ", ".join(os.path.basename(i.path) for i in session.loaded),
              file=sys.stderr)
    print("Type a request, or /help. Ctrl-C stops a turn; /exit ends the session.",
          file=sys.stderr)
    while True:
        try:
            text = _read_request()
        except (EOFError, KeyboardInterrupt):
            print(file=sys.stderr)
            return 0
        if not text:
            continue
        out = slash.dispatch(session, text)
        if out is slash.EXIT:
            return 0
        if out is not None:
            print(out)
            continue
        try:
            run_turn(session, text)
        except KeyboardInterrupt:
            print("\n[turn stopped]", file=sys.stderr)


def main(argv: "list[str] | None" = None) -> int:
    args = parse_args(argv)
    interactive = args.prompt is None
    session = build_session(args, approver=prompt_approver if interactive else deny_all,
                            on_event=print_event)
    if session.agent.live_backend() is None:
        print(NO_BACKEND, file=sys.stderr)
        return 2
    if not interactive:
        return run_turn(session, args.prompt)
    return repl(session)


if __name__ == "__main__":
    raise SystemExit(main())
