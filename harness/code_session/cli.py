"""`flywheel code`: an interactive coding session in the current folder.

  flywheel code                      start a session here
  flywheel code -p "fix the test"    run one request and exit
  flywheel code --mode edit          writes run without asking; commands still ask

Every turn runs the gated tool loop and lands on one hash-chained ledger.
Type /help inside the session for the commands.
"""
from __future__ import annotations

import json
import os
import sys

from . import resume, slash
from .args import parse_args  # noqa: F401 (re-exported: tests and callers use cli.parse_args)
from .attach import attach_hooks as _attach_hooks, attach_mcp as _attach_mcp
from .rules import load_rules
from .store import ResumeRefused
from .backends import build_agent, describe, ladder
from .policy import deny_all
from .session import new_session

NO_BACKEND = ("No model is reachable. Set a provider key (for example "
              "ANTHROPIC_API_KEY or OPENAI_API_KEY), start a local server such as "
              "ollama, or put the claude or codex CLI on PATH. `flywheel doctor` "
              "shows what is set.")


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


def plain_output() -> bool:
    """Screen-reader friendly output: FLYWHEEL_SCREEN_READER=1, or --plain."""
    return os.environ.get("FLYWHEEL_SCREEN_READER", "") not in ("", "0")


def print_event(event: dict) -> None:
    kind, plain = event.get("type"), plain_output()
    if kind == "tool_call":
        args = json.dumps(event.get("args", {}), ensure_ascii=False)
        lead = "Tool call: " if plain else "  > "
        print(f"{lead}{event.get('name')} {args[:160]}", file=sys.stderr)
    elif kind == "tool_result":
        first = (event.get("output") or "").strip().splitlines()[:1]
        words = ("succeeded", "failed") if plain else ("ok", "FAIL")
        mark = words[0] if event.get("ok") else words[1]
        lead = "Tool result, " if plain else "    "
        print(f"{lead}{mark}: {first[0][:160] if first else ''}", file=sys.stderr)


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
    root = args.root
    session = new_session(agent, root, mode=args.mode, approver=approver,
                          runner=runner if runner is not None else _runner(),
                          max_steps=args.max_steps, test_cmd=args.test_cmd or None,
                          on_event=on_event)
    home = _home()
    rules = load_rules(root, home)
    if rules.errors:
        raise ResumeRefused("permission rules could not be read, so none are trusted: "
                            + "; ".join(rules.errors))
    session_id = resume.pick_id(args, home)
    if session_id:
        resume.restore(session, home, session_id)
    session.compact_budget = args.compact_budget
    session.set_rules(rules)
    from .skills import load_skills
    session.set_skills(load_skills(root, home))
    from .commands import load_commands
    session.commands = load_commands(root, home, reserved=tuple(slash.COMMANDS))
    _attach_hooks(session, root, home, interactive=approver is prompt_approver,
                  trust=args.trust_project_hooks)
    if not args.no_mcp:
        _attach_mcp(session, root, home, interactive=approver is prompt_approver,
                    trust=args.trust_project_mcp)
    if not args.no_instructions:
        session.load_instructions(home)
    if not args.no_save:
        session.home = home
    return session


def footer(result) -> str:
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
    print(footer(result), file=sys.stderr)
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
        if isinstance(out, slash.Turn):
            text, out = str(out), None
        if out is not None:
            print(out)
            continue
        try:
            run_turn(session, text)
        except KeyboardInterrupt:
            print("\n[turn stopped]", file=sys.stderr)


def _serve_acp(args) -> int:
    import copy
    from .acp_agent import serve

    def make_session(cwd: str):
        local = copy.copy(args)
        local.root = os.path.abspath(cwd)
        return build_session(local, approver=deny_all, on_event=None)
    return serve(make_session)


def main(argv: "list[str] | None" = None) -> int:
    args = parse_args(argv)
    if args.plain:
        os.environ["FLYWHEEL_SCREEN_READER"] = "1"
    if args.sessions:
        print(resume.render_list(_home(), args.root))
        return 0
    if args.acp:
        return _serve_acp(args)
    interactive = args.prompt is None
    worktree = None
    if args.worktree:
        from .worktree import WorktreeError, open_worktree
        try:
            worktree = open_worktree(args.root, args.worktree)
        except WorktreeError as e:
            print(f"[refused] {e}", file=sys.stderr)
            return 2
        args.root = worktree.path
        print(f"[worktree] {worktree.path} on branch {worktree.branch}"
              f"{f' ({len(worktree.carried)} uncommitted file(s) carried)' if worktree.carried else ''}",
              file=sys.stderr)
    try:
        session = build_session(args, approver=prompt_approver if interactive else deny_all,
                                on_event=print_event)
    except ResumeRefused as e:
        print(f"[refused] {e}", file=sys.stderr)
        return 2
    if worktree is not None:
        session.ledger.append("worktree", json.dumps(worktree.record(), sort_keys=True),
                              {"created": worktree.created})
    session.fire("SessionStart")
    try:
        if session.agent.live_backend() is None:
            print(NO_BACKEND, file=sys.stderr)
            return 2
        if not interactive:
            from .print_mode import run_print
            return run_print(session, args.prompt, args.output_format)
        return repl(session)
    finally:
        session.fire("SessionEnd")
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
