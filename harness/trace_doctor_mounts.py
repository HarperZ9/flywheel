"""Doctor check 1: which Claude Code and Codex hook mounts reach Flywheel.

Only hook entries are parsed (SP-33). Settings files can hold API keys in an
`env` block, so no other value is printed, logged or compared; from `env`
blocks the check reports only the names of FLYWHEEL_* variables that are set.
Nothing named in a settings file is run: an interpreter is checked by looking
for its file, and the hook module by importing it in this process.
"""
from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil

MODULE = "harness.capture_hooks"
LEGACY = ("wrapper_turn_receipt_hook.py", "wrapper_scaffold_hook.py")


@dataclass(frozen=True)
class Mount:
    label: str
    event: str
    form: str        # module, legacy-script
    problem: str     # "" when it resolves
    target: str      # module name or script file name, never the whole command


def settings_files(environ, cwd: Path) -> list[tuple[str, Path]]:
    from harness.capture_hooks.home import profile_dir
    profile = profile_dir() or Path.home()
    claude = Path(environ.get("CLAUDE_CONFIG_DIR") or profile / ".claude")
    codex = Path(environ.get("CODEX_HOME") or profile / ".codex")
    return [("claude settings.json", claude / "settings.json"),
            ("project .claude/settings.json", cwd / ".claude" / "settings.json"),
            ("project .claude/settings.local.json", cwd / ".claude" / "settings.local.json"),
            ("codex hooks.json", codex / "hooks.json"),
            ("codex config.toml", codex / "config.toml"),
            ("project .codex/hooks.json", cwd / ".codex" / "hooks.json"),
            ("project .codex/config.toml", cwd / ".codex" / "config.toml")]


def _load(path: Path):
    raw = path.read_bytes()
    if path.suffix == ".toml":
        import tomllib
        return tomllib.loads(raw.decode("utf-8"))
    return json.loads(raw)


def _commands(doc) -> list[tuple[str, str]]:
    hooks = doc.get("hooks") if type(doc) is dict else None
    out = []
    for event, groups in (hooks.items() if type(hooks) is dict else []):
        for group in groups if type(groups) is list else []:
            for hook in (group.get("hooks") or []) if type(group) is dict else []:
                command = hook.get("command") if type(hook) is dict else None
                if type(command) is str:
                    out.append((str(event), command))
    return out


def _interpreter_problem(program: str) -> str:
    found = program if os.path.isabs(program) and os.path.isfile(program) else (
        shutil.which(program))
    return "" if found else "interpreter not found"


ISOLATION = ("the project folder or PYTHONPATH can replace the hook: "
             "mount with -P -E as flywheel traces hooks print-mount shows")


def _isolated(flags: list[str]) -> bool:
    """True when the interpreter flags before -m include -I, or both -P
    and -E (single or combined, as in -PE)."""
    letters = "".join(f[1:] for f in flags if f.startswith("-") and not f.startswith("--"))
    return "I" in letters or ("P" in letters and "E" in letters)


def classify(label: str, event: str, command: str) -> Mount | None:
    try:
        words = shlex.split(command, posix=os.name != "nt")
    except ValueError:
        return None
    words = [w.strip('"') for w in words]
    if "-m" in words and words.index("-m") + 1 < len(words):
        module = words[words.index("-m") + 1]
        if module.startswith(MODULE):
            problem = _interpreter_problem(words[0])
            if module != MODULE or importlib.util.find_spec(MODULE) is None:
                problem = problem or "module not importable"
            if not _isolated(words[1:words.index("-m")]):
                problem = problem or ISOLATION
            return Mount(label, event, "module", problem, module)
    for word in words:
        name = Path(word).name
        if name in LEGACY:
            problem = "" if Path(word).is_file() else "script not found"
            return Mount(label, event, "legacy-script", problem, name)
    return None


def scan(environ, cwd: Path) -> tuple[list[Mount], list[str], list[str]]:
    """(mounts, labels of files read, FLYWHEEL_* names set in env blocks)."""
    mounts, read, names = [], [], set()
    for label, path in settings_files(environ, Path(cwd)):
        if not path.is_file():
            continue
        try:
            doc = _load(path)
        except (OSError, ValueError, UnicodeError):
            read.append(f"{label} (unreadable)")
            continue
        read.append(label)
        env = doc.get("env") if type(doc) is dict else None
        env = env if type(env) is dict else {}
        names |= {k for k in env if type(k) is str and k.startswith("FLYWHEEL_")}
        for event, command in _commands(doc):
            mount = classify(label, event, command)
            if mount is not None:
                mounts.append(mount)
    return mounts, read, sorted(names)
