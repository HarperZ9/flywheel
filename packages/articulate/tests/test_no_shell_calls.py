"""No source call asks for a command shell on its own.

The batch path does run cmd.exe, because Windows starts every .cmd file that
way, and tests/test_claude_cli_batch.py guards what reaches it. This scan
covers the other ways a call can reach a shell: the shell functions in os and
asyncio, a shell= keyword, keywords passed through **, a command whose first
word names a shell, COMSPEC, and os.posix_spawn. Each rule has a sample below
that it must catch, so a rule that stops matching fails here.
"""
import ast
import pathlib

_SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "articulate"
_SHELL_FUNCS = {"system", "popen", "startfile", "getoutput", "getstatusoutput",
                "create_subprocess_shell"}
_PROCESS_FUNCS = {"Popen", "run", "call", "check_call", "check_output",
                  "create_subprocess_exec"}
_SHELLS = {"cmd", "command", "powershell", "pwsh", "sh", "bash", "dash", "zsh",
           "ksh", "fish", "comspec"}


def _shell_word(node):
    """True when a literal command, or its first element, names a shell."""
    if isinstance(node, (ast.List, ast.Tuple)) and node.elts:
        node = node.elts[0]
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.strip():
        word = node.value.split()[0].replace("\\", "/").rsplit("/", 1)[-1].lower()
        return word.rsplit(".", 1)[0] in _SHELLS if word.endswith((".exe", ".com")) \
            else word in _SHELLS
    return False


class _ShellCalls(ast.NodeVisitor):
    def __init__(self):
        self.found = []

    def _flag(self, what, node):
        self.found.append(f"{what} at line {node.lineno}")

    def visit_Constant(self, node):
        if isinstance(node.value, str) and node.value.strip().upper() in ("COMSPEC", "%COMSPEC%"):
            self._flag("COMSPEC", node)

    def visit_Call(self, node):
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name in _SHELL_FUNCS or name.startswith(("spawn", "exec", "posix_spawn")) \
                and name != "exec_module":
            self._flag(f"{name}()", node)
        for kw in node.keywords:
            if kw.arg == "shell" and not (isinstance(kw.value, ast.Constant) and kw.value.value is False):
                self._flag("shell=", node)
            if kw.arg is None and name in _PROCESS_FUNCS:
                self._flag(f"{name}(**...)", node)
        if name in _PROCESS_FUNCS and node.args and _shell_word(node.args[0]):
            self._flag(f"{name}() of a shell", node)
        self.generic_visit(node)


def _scan(source):
    visitor = _ShellCalls()
    visitor.visit(ast.parse(source))
    return visitor.found


def test_no_source_call_asks_for_a_shell():
    for path in sorted(_SRC.rglob("*.py")):
        assert _scan(path.read_text(encoding="utf-8")) == [], path.name


def test_the_shell_check_catches_what_it_claims():
    samples = [
        "os.system('x')", "os.popen('x')", "subprocess.run(a, shell=True)",
        "subprocess.run(a, shell=flag)", "os.spawnl(0, 'x')", "os.execv('x', [])",
        "subprocess.Popen(a, **{'shell': True})", "subprocess.run(a, **opts)",
        "subprocess.Popen(['cmd.exe', '/d', '/c', *argv])",
        "subprocess.run([r'C:\\Windows\\System32\\cmd.exe', '/c', x])",
        "subprocess.run(('powershell', '-c', x))", "subprocess.run(['pwsh.exe', x])",
        "subprocess.check_output('bash -c x')", "subprocess.call(['/bin/sh', '-c', x])",
        "subprocess.run([os.environ['COMSPEC'], '/c', x])", "os.getenv('ComSpec')",
        "os.posix_spawn('x', [], {})", "os.posix_spawnp('x', [], {})",
    ]
    for sample in samples:
        assert _scan(sample), sample


def test_the_shell_check_passes_ordinary_calls():
    controls = ["subprocess.run(a, shell=False)", "subprocess.run([taskkill(), '/F', pid])",
                "subprocess.Popen(argv, cwd=d, env=e, start_new_session=True)",
                "subprocess.run(['git', 'status'])", "dict(**opts)", "f(**kw)"]
    for sample in controls:
        assert _scan(sample) == [], sample
