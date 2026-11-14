"""A static scan of one module's source for ways to start a child process.

`spawn_problems(name, text)` returns what in the source starts, or could
start, a child outside the Lean allow-list (harness.lean_env). It reads the
syntax tree and resolves names through the module's own imports, so
`import subprocess as sp; sp.run(...)` and `from subprocess import Popen`
are seen as what they are.

What it reports:

  - a call to `subprocess.run`, `Popen`, `call`, `check_call`, `check_output`,
    `asyncio.create_subprocess_exec` or `_shell`, or `spawn_killable`, whose
    `env=` is not exactly a call to `lean_env(...)`. An environment built
    around the allow-list (`{**lean_env(), ...}`, `os.environ | lean_env()`)
    is not the allow-list and is reported;
  - any use of a function that cannot take an environment or takes it by
    position: `os.system`, `os.popen`, `os.startfile`, `os.spawn*`, `os.exec*`,
    `os.posix_spawn*`, `os.fork*`, `subprocess.getoutput`,
    `subprocess.getstatusoutput`, `pty.spawn`, `pty.fork`;
  - any mention of a spawn function that is not a direct call of it (an
    alias such as `run = subprocess.run`, or passing it as a value);
  - `getattr` on `subprocess`, `os`, `asyncio`, `multiprocessing` or `pty`;
  - an import of `multiprocessing`, `pty` or `concurrent.futures`, and a
    star import from `subprocess`, `os` or `asyncio`;
  - a copy of the parent environment: `dict(os.environ)`, `**os.environ`,
    `env=os.environ`, `os.environ.copy()`.

What it does not see: a process started through `ctypes` (the Windows
sandbox calls CreateProcess that way and is tested at its call site), through
`importlib`, `__import__`, `eval` or `exec`, through a name reached by a
second assignment (`m = subprocess; m.run(...)` is reported as a use of the
module only when an attribute of it is taken directly), or by another module
that a Lean module calls.
"""
import ast

_WITH_ENV = {"subprocess.run", "subprocess.Popen", "subprocess.check_output", "subprocess.call",
             "subprocess.check_call", "asyncio.create_subprocess_exec",
             "asyncio.create_subprocess_shell", "asyncio.subprocess.create_subprocess_exec",
             "asyncio.subprocess.create_subprocess_shell", "spawn_killable",
             "lean_replay.spawn_killable"}
_NO_ENV = {"os.system", "os.popen", "os.startfile", "os.fork", "os.forkpty",
           "subprocess.getoutput", "subprocess.getstatusoutput", "pty.spawn", "pty.fork"}
_NO_ENV_PREFIX = ("os.spawn", "os.exec", "os.posix_spawn")
_MODULES = {"subprocess", "os", "asyncio", "multiprocessing", "pty"}
_BANNED_IMPORTS = ("multiprocessing", "pty", "concurrent.futures")
_COPIES = ("dict(os.environ)", "**os.environ", "env=os.environ", "os.environ.copy()")


def _aliases(tree) -> tuple:
    """({local name: dotted name it stands for}, import problems)."""
    names, problems = {}, []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names[alias.asname or alias.name.split(".")[0]] = (
                    alias.name if alias.asname else alias.name.split(".")[0])
                if alias.name.startswith(_BANNED_IMPORTS):
                    problems.append((node.lineno, f"import of {alias.name}"))
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith(_BANNED_IMPORTS):
                problems.append((node.lineno, f"import from {node.module}"))
            for alias in node.names:
                if alias.name == "*" and node.module.split(".")[0] in _MODULES:
                    problems.append((node.lineno, f"star import from {node.module}"))
                names[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return names, problems


def _dotted(node, names: dict) -> str:
    """The dotted name an expression stands for, through the import aliases, or ''."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return ""
    return ".".join([names.get(node.id, node.id), *reversed(parts)])


def _spawner(dotted: str) -> str:
    """'env' for a spawn function that takes env=, 'bare' for one that cannot, else ''."""
    if dotted in _WITH_ENV or dotted.rsplit(".", 1)[-1] == "spawn_killable":
        return "env"                    # spawn_killable, from whichever module it was imported
    if dotted in _NO_ENV or dotted.startswith(_NO_ENV_PREFIX):
        return "bare"
    return ""


def _is_allow_list(env, names: dict) -> bool:
    return isinstance(env, ast.Call) and _dotted(env.func, names) in (
        "lean_env", "lean_env.lean_env", "harness.lean_env.lean_env")


def spawn_problems(name: str, text: str) -> list:
    """What in one module's source starts a child outside the allow-list."""
    tree = ast.parse(text)
    names, found = _aliases(tree)
    problems = [f"{name}: {bad}" for bad in _COPIES if bad in text]
    called = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        dotted = _dotted(node.func, names)
        kind = _spawner(dotted)
        if kind:
            called.add(id(node.func))
        if kind == "bare":
            found.append((node.lineno, f"{dotted} cannot take an environment"))
        elif kind == "env":
            env = next((k.value for k in node.keywords if k.arg == "env"), None)
            if env is None or not _is_allow_list(env, names):
                found.append((node.lineno, "a spawn without lean_env"))
        elif dotted == "getattr" and node.args and _dotted(node.args[0], names) in _MODULES:
            found.append((node.lineno, f"getattr on {_dotted(node.args[0], names)}"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Attribute, ast.Name)) and id(node) not in called:
            dotted = _dotted(node, names)
            if _spawner(dotted):
                found.append((node.lineno, f"{dotted} used other than by calling it"))
    return problems + [f"{name}:{line}: {what}" for line, what in sorted(set(found))]
