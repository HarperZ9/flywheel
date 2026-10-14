"""slash.py -- the session's slash commands.

Each handler takes the session and the argument text and returns the text to
show. A handler never talks to the model; the commands steer the session, the
model does the work.
"""
from __future__ import annotations

import json
import subprocess

from . import instructions as _instructions
from .backends import set_model
from .policy import MODES

EXIT = object()      # returned by /exit so the loop can stop


def _help(_s, _a):
    lines = ["Commands:"]
    for name, (_fn, text) in sorted(COMMANDS.items()):
        lines.append(f"  /{name:<8} {text}")
    lines.append("Anything else is a request to the agent.")
    return "\n".join(lines)


def _exit(_s, _a):
    return EXIT


def _clear(s, _a):
    s.clear()
    return "conversation cleared; the ledger keeps the record"


def _mode(s, arg):
    arg = arg.strip()
    if not arg:
        return f"mode: {s.executor.mode} (choose one of {', '.join(MODES)})"
    if arg not in MODES:
        return f"unknown mode {arg!r}; choose one of {', '.join(MODES)}"
    s.set_mode(arg)
    return f"mode: {arg}"


def _model(s, arg):
    arg = arg.strip()
    if not arg:
        return f"model: {s.status()['backend']}"
    try:
        return f"model: {set_model(s.agent, arg)}"
    except ValueError as e:
        return f"[error] {e}"


def _status(s, _a):
    return json.dumps(s.status(), indent=2)


def _diff(s, _a):
    from harness import safe_program
    try:
        argv, env = safe_program.launch(["git", "diff", "--stat"], cwd=s.root)
        out = subprocess.run(argv, cwd=s.root, env=env, capture_output=True,
                             text=True, timeout=30)
    except (OSError, subprocess.SubprocessError, safe_program.ProgramUnavailable) as e:
        return f"[error] git diff did not run: {e.__class__.__name__}"
    return (out.stdout or out.stderr or "").strip() or "(no changes against the index)"


def _undo(s, _a):
    restored = s.undo()
    if restored is None:
        return "nothing to undo (changes made by commands are not tracked)"
    return "restored: " + ", ".join(r["path"] for r in restored)


def _sessions(s, _a):
    if not s.home:
        return "this session is not being saved (--no-save)"
    from .resume import render_list
    head = f"this session: {s.session_id or '(saved after the first turn)'}"
    return head + "\n" + render_list(s.home, s.root)


def _todo(s, _a):
    from .policy import render_todos
    return render_todos(s.executor.todos)


def _cost(s, _a):
    u = s.usage
    line = (f"{u['model_calls']} model call(s): {u['input_tokens']} input and "
            f"{u['output_tokens']} output tokens as the provider reported them")
    if u["uncounted_calls"]:
        line += f"; {u['uncounted_calls']} call(s) reported no token counts and are not estimated"
    return line + ". No price is applied: prices change, and a dated price is not on file."


def _init(s, _a):
    ok, message = _instructions.write_init(s.root)
    return message


COMMANDS = {
    "help": (_help, "list commands"),
    "exit": (_exit, "end the session"),
    "clear": (_clear, "forget the conversation (the ledger keeps it)"),
    "mode": (_mode, "show or set the permission mode: plan, ask, edit, auto"),
    "model": (_model, "show or set the model on the live backend"),
    "status": (_status, "folder, mode, backend, turns, ledger head, instruction files"),
    "diff": (_diff, "git diff --stat of the working tree"),
    "undo": (_undo, "put back the files the last changing turn wrote"),
    "sessions": (_sessions, "saved sessions for this folder"),
    "todo": (_todo, "the agent's todo list for this session"),
    "cost": (_cost, "tokens used this session, as the provider reported them"),
    "init": (_init, "draft an AGENTS.md for this folder (never overwrites)"),
}


def dispatch(session, line: str):
    """Run a slash command. Returns its text, EXIT, or None if `line` is not one."""
    if not line.startswith("/"):
        return None
    name, _, arg = line[1:].partition(" ")
    entry = COMMANDS.get(name)
    if entry is None:
        return f"unknown command /{name}; /help lists them"
    return entry[0](session, arg)
