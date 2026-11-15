"""Find and start the claude CLI for the editor layer.

The optional `claude-cli` editor backend runs the model through the Claude CLI
in headless mode. Two things break a bare "claude" on Windows. A process that
a bundler or an MCP host starts can inherit a PATH that holds only System32.
And subprocess without a shell asks CreateProcess for the name, which appends
.exe and never finds the claude.cmd shim that an npm install puts on the PATH.

So the CLI path comes from ARTICULATE_CLAUDE_CLI when that variable is set, and
the value must be an absolute path. Otherwise the resolver walks the absolute
PATH entries itself. It looks for claude.exe in every entry first and falls back
to a batch shim only when no claude.exe exists. It never searches the current
directory: shutil.which does on Windows, so a document repo that ships a file
named claude.cmd would run in place of the real CLI. When nothing runnable is
found, the caller gets ClaudeUnavailable, whose message names the variable. No
message here prints the value of the variable or the resolved path.

The prompt always travels in a temporary file passed with
--append-system-prompt-file, and argv holds a fixed line, that path and fixed
flags. A long prompt would pass the Windows command-line limit or the Linux
per-argument limit. And a .cmd or .bat file runs under cmd.exe, which parses
its arguments a second time: it cuts one at the first newline and reads
% ^ & | < > ! as commands, and ")" too when the argument is not quoted. For a
batch file every argument is checked before the start, and a path that holds
one of those characters is refused.

The document is untrusted input. Every call turns off the built-in tools, all
MCP servers and the project and local settings. The CLI reads those settings,
hooks included, from its working directory, and -p skips the trust prompt. So
the child runs in a private empty folder, never in the caller's. On Windows the
child also gets NoDefaultCurrentDirectoryInExePath=1: an npm claude.cmd shim
runs "node" by bare name, and cmd.exe would look for it in the working folder
first. A timeout stops the whole process tree, since a batch shim runs the CLI
as a grandchild that would otherwise keep the pipes open.
"""
import ntpath
import json
import os
import posixpath
import shutil
import signal
import subprocess
import sys
import tempfile

ENV_VAR = "ARTICULATE_CLAUDE_CLI"
DEFAULT_NAME = "claude"
BATCH_SUFFIXES = (".cmd", ".bat")
# Suffixes CreateProcess can start. PATHEXT may also list .js or .py, which it cannot.
_STARTABLE = (".com", ".exe") + BATCH_SUFFIXES
CMD_UNSAFE = frozenset('"%^&|<>!\r\n')
# cmd.exe ends a parenthesized block at ")" outside quotes. Python quotes an
# argument only when it holds a space or a tab, so these count only without one.
CMD_UNSAFE_UNQUOTED = frozenset(")")
FIXED_PROMPT = ("Apply the instructions in your system prompt to the document "
                "on standard input.")
# User settings only, no MCP server and no built-in tool. "--tools" takes a
# list, so it goes last.
LOCKDOWN = ("--setting-sources", "user", "--strict-mcp-config", "--tools", "")
# The CLI version these flags were checked against. The first version that
# accepts all of them is unknown.
TESTED_CLI_VERSION = "2.1.251"
NO_CWD_SEARCH = "NoDefaultCurrentDirectoryInExePath"
DRAIN_SECONDS = 5

_MISSING = (f"claude CLI not found. The claude CLI must be installed and logged in "
            f"(run `claude login`). Put it on PATH, or set {ENV_VAR} to the full "
            f"path of the claude executable.")
_BAD_VAR = (f"{ENV_VAR} is set, but it does not name a runnable file by an absolute "
            f"path. Set it to the full path of the claude executable, which must be "
            f"installed and logged in.")
_UNSAFE_BATCH = (f"the claude CLI resolves to a Windows batch file, and its path or "
                 f"the temporary folder's path holds characters that cmd.exe would "
                 f"reinterpret. Set {ENV_VAR} to the full path of a native claude "
                 f"executable, or point TEMP at a plain folder.")


class ClaudeUnavailable(RuntimeError):
    """The model backend could not be reached (missing CLI, credits, auth, rate limit)."""


def _runnable(path):
    return os.path.isfile(path) and os.access(path, os.X_OK)


def _is_absolute(path, windows):
    # On Windows "\tools" hangs off the current drive, so it needs a drive or share too.
    if windows:
        return ntpath.isabs(path) and bool(ntpath.splitdrive(path)[0])
    return posixpath.isabs(path)


def _suffixes(env):
    listed = (env.get("PATHEXT") or ".COM;.EXE;.BAT;.CMD").split(";")
    return [s for s in listed if s.lower() in _STARTABLE]


def _from_variable(configured, exists, windows, suffixes):
    if not _is_absolute(configured, windows):
        raise ClaudeUnavailable(_BAD_VAR)
    candidates = [configured]
    if windows:
        if ntpath.splitext(configured)[1].lower() not in _STARTABLE:
            candidates = [configured + s for s in suffixes]
    found = next((c for c in candidates if exists(c)), None)
    if not found:
        raise ClaudeUnavailable(_BAD_VAR)
    return found


def _from_path(env, exists, windows, suffixes):
    sep, join = (";", ntpath.join) if windows else (":", posixpath.join)
    dirs = [d.strip().strip('"') for d in (env.get("PATH") or "").split(sep)]
    dirs = [d for d in dirs if d and _is_absolute(d, windows)]
    if windows:
        # claude.exe anywhere on the PATH beats a batch shim earlier on it.
        names = [[DEFAULT_NAME + ".exe"], [DEFAULT_NAME + s for s in suffixes]]
    else:
        names = [[DEFAULT_NAME]]
    for group in names:
        for d in dirs:
            for name in group:
                if exists(join(d, name)):
                    return join(d, name)
    raise ClaudeUnavailable(_MISSING)


def resolve(environ=None, exists=None, windows=None):
    """Return the absolute path of the claude CLI, or raise ClaudeUnavailable."""
    env = os.environ if environ is None else environ
    exists = _runnable if exists is None else exists
    windows = os.name == "nt" if windows is None else windows
    suffixes = _suffixes(env) if windows else []
    configured = (env.get(ENV_VAR) or "").strip()
    if configured:
        return _from_variable(configured, exists, windows, suffixes)
    return _from_path(env, exists, windows, suffixes)


def is_batch(path, windows=None):
    """True when Windows would start this file through cmd.exe."""
    windows = os.name == "nt" if windows is None else windows
    return windows and os.path.splitext(path)[1].lower() in BATCH_SUFFIXES


def cmd_unsafe(arg):
    """True when cmd.exe would read part of this argument as a command."""
    if CMD_UNSAFE.intersection(arg):
        return True
    quoted = not arg or " " in arg or "\t" in arg
    return not quoted and bool(CMD_UNSAFE_UNQUOTED.intersection(arg))


def _make_session(prompt, tmpdir):
    """A private folder holding the prompt file and an empty working folder."""
    session = tempfile.mkdtemp(prefix="articulate-", dir=tmpdir)
    try:
        cwd = os.path.join(session, "cwd")
        os.mkdir(cwd)
        prompt_file = os.path.join(session, "prompt.txt")
        with open(prompt_file, "x", encoding="utf-8", newline="") as fh:
            fh.write(prompt)
    except BaseException:
        _remove_quietly(session)
        raise
    return session, cwd, prompt_file


def _remove_quietly(path):
    try:
        shutil.rmtree(path)
    except OSError as exc:
        # A leftover temp folder is not worth failing a finished model call. Say
        # so, since it holds the prompt.
        print(f"[editor] could not remove a temporary prompt folder ({exc.strerror})",
              file=sys.stderr)


def _child_env(windows):
    """The child's environment: inherited, plus no current-directory search on Windows."""
    if not windows:
        return None
    # Windows names are case-insensitive, so drop any other spelling first.
    env = {k: v for k, v in os.environ.items() if k.lower() != NO_CWD_SEARCH.lower()}
    env[NO_CWD_SEARCH] = "1"
    return env


def _taskkill():
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(260)
        if ctypes.windll.kernel32.GetSystemDirectoryW(buf, 260):
            return os.path.join(buf.value, "taskkill.exe")
    except (ImportError, AttributeError, OSError):
        pass  # fall back to the documented default location below
    root = os.environ.get("SystemRoot") or r"C:\Windows"
    return os.path.join(root, "System32", "taskkill.exe")


def _stop_tree(proc):
    """Stop the child and everything it started."""
    if os.name == "nt":
        try:
            subprocess.run([_taskkill(), "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, timeout=DRAIN_SECONDS, check=False)
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"[editor] could not stop the claude process tree "
                  f"({type(exc).__name__}); stopping the direct child only",
                  file=sys.stderr)
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass  # the group has already exited
    if proc.poll() is None:
        proc.kill()


def _bounded_run(argv, input=None, timeout=None, cwd=None, env=None):
    """subprocess.run, except that a timeout stops the whole process tree."""
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, encoding="utf-8",
                            cwd=cwd, env=env, start_new_session=os.name != "nt")
    try:
        out, err = proc.communicate(input, timeout=timeout)
    except subprocess.TimeoutExpired:
        _stop_tree(proc)
        try:
            out, err = proc.communicate(timeout=DRAIN_SECONDS)
        except subprocess.TimeoutExpired:
            print("[editor] the claude process tree still holds its pipes after "
                  "the timeout", file=sys.stderr)
            out = err = None
        # The CLI name only: the argv holds the resolved path.
        raise subprocess.TimeoutExpired(DEFAULT_NAME, timeout, output=out, stderr=err) from None
    except BaseException:
        _stop_tree(proc)
        raise
    return subprocess.CompletedProcess(argv, proc.returncode, out, err)


def run(prompt, text, timeout=600, environ=None, exists=None,
        runner=None, windows=None, tmpdir=None):
    """Run `claude -p` with the prompt in a file and the document on stdin.

    The child starts in a private empty folder. Returns the CompletedProcess.
    Raises ClaudeUnavailable when the CLI cannot be found or started, or the
    prompt file cannot be written, and lets subprocess.TimeoutExpired through.
    """
    windows = os.name == "nt" if windows is None else windows
    cli = resolve(environ, exists, windows)
    runner = _bounded_run if runner is None else runner
    try:
        session, cwd, prompt_file = _make_session(prompt, tmpdir)
    except OSError as exc:
        # strerror carries the reason; the filename, which is the path, stays out.
        raise ClaudeUnavailable(f"the prompt file could not be written to the temporary "
                                f"folder ({_reason(exc)})") from exc
    try:
        argv = [cli, "-p", FIXED_PROMPT, "--append-system-prompt-file", prompt_file,
                *LOCKDOWN]
        if is_batch(cli, windows) and any(cmd_unsafe(a) for a in argv):
            raise ClaudeUnavailable(_UNSAFE_BATCH)
        try:
            return runner(argv, input=text, timeout=timeout, cwd=cwd, env=_child_env(windows))
        except OSError as exc:
            raise ClaudeUnavailable(
                f"the claude CLI could not be started ({_reason(exc)}). It must be "
                f"installed and logged in; {ENV_VAR} can name its full path.") from exc
    finally:
        _remove_quietly(session)


def _reason(exc):
    return exc.strerror or type(exc).__name__


def auth_status(timeout=15, environ=None, exists=None, runner=None, windows=None, tmpdir=None):
    """Read authentication metadata without a model call or document settings.

    Reuses the same absolute executable resolution, isolated working directory,
    Windows argument check, and process-tree timeout as completions.
    """
    windows = os.name == 'nt' if windows is None else windows
    cli = resolve(environ, exists, windows)
    runner = _bounded_run if runner is None else runner
    try:
        session, cwd, _ = _make_session('', tmpdir)
    except OSError:
        raise ClaudeUnavailable('claude CLI auth preflight could not create a temporary folder') from None
    try:
        argv = [cli, 'auth', 'status', '--json']
        if is_batch(cli, windows) and any(cmd_unsafe(arg) for arg in argv):
            raise ClaudeUnavailable(_UNSAFE_BATCH)
        try:
            result = runner(argv, timeout=timeout, cwd=cwd, env=_child_env(windows))
            status = json.loads(result.stdout)
            if not isinstance(status, dict) or not isinstance(status.get('loggedIn'), bool):
                raise ValueError
            return {'loggedIn':status['loggedIn'], **({'subscriptionType':status['subscriptionType']}
                    if 'subscriptionType' in status else {})}
        except (OSError, ValueError, TypeError):
            raise ClaudeUnavailable('claude CLI auth status unavailable') from None
    finally:
        _remove_quietly(session)


_BACKEND_ERRORS = (
    ("credit balance is too low", "credit balance too low; add credits or set ANTHROPIC_API_KEY"),
    ("rate limit", "rate limited; wait for the weekly reset"),
    ("not authenticated", "claude CLI not authenticated; run `claude login`"),
    ("invalid api key", "claude CLI auth invalid"),
)


def raise_for_failed_call(out, err):
    """Raise for a call that exited nonzero: ClaudeUnavailable for a known cause."""
    # Only a failed call is searched for these phrases. A finished rewrite of a
    # document about rate limits holds the words too, and it must come back.
    blob = (out + " " + err).lower()
    for sentinel, msg in _BACKEND_ERRORS:
        if sentinel in blob:
            raise ClaudeUnavailable(f"claude CLI: {msg}")
    if "unknown option" in err.lower():
        raise ClaudeUnavailable(
            f"claude CLI: this version rejects a flag articulate passes. Upgrade the "
            f"claude CLI; articulate is tested with version {TESTED_CLI_VERSION}.")
    raise RuntimeError(f"claude CLI failed: {(err or out)[:300] or 'unknown error'}")
