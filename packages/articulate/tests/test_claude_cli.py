"""The editor finds the claude CLI through ARTICULATE_CLAUDE_CLI or the PATH.

A bundled child process can start with a PATH that holds only System32, and
subprocess without a shell does not turn "claude" into claude.cmd on Windows. So
the editor resolves the CLI itself: the environment variable first, which must
be an absolute path, then the absolute PATH entries, with claude.exe ahead of
any batch shim. The current directory is never searched, and the child runs in
a private empty folder with project settings off. No test here starts a
process; a fake runner records what would run, and a fake file table stands in
for the disk.
"""
import ntpath
import os
import posixpath

import pytest

from articulate import claude_cli
from cli_fakes import _LOCKDOWN_EXPECTED, _SECRET, _Disk, _Runner, work  # noqa: F401


def _posix(*paths):
    return _Disk(*paths)


def test_the_environment_variable_wins_over_the_path():
    disk = _posix("/opt/tools/claude", "/usr/bin/claude")
    env = {claude_cli.ENV_VAR: "/opt/tools/claude", "PATH": "/usr/bin"}
    assert claude_cli.resolve(env, disk, windows=False) == "/opt/tools/claude"


@pytest.mark.parametrize("value", ["claude", "./claude", "tools/claude"])
def test_a_relative_variable_is_refused_even_when_the_file_exists(value):
    disk = _posix(value, "/usr/bin/claude")
    with pytest.raises(claude_cli.ClaudeUnavailable) as info:
        claude_cli.resolve({claude_cli.ENV_VAR: value, "PATH": "/usr/bin"}, disk, windows=False)
    assert claude_cli.ENV_VAR in str(info.value)
    assert disk.probed == [], "a relative value must not be looked up at all"


@pytest.mark.parametrize("value", [r"claude.cmd", r".\claude.cmd", r"\tools\claude.exe"])
def test_a_windows_variable_needs_a_drive_or_share(value):
    disk = _Disk(value)
    with pytest.raises(claude_cli.ClaudeUnavailable):
        claude_cli.resolve({claude_cli.ENV_VAR: value}, disk, windows=True)


def test_a_windows_variable_without_a_suffix_gets_a_runnable_one():
    disk = _Disk(r"C:\tools\claude", r"C:\tools\claude.EXE")
    env = {claude_cli.ENV_VAR: r"C:\tools\claude", "PATHEXT": ".COM;.EXE;.BAT;.CMD"}
    assert claude_cli.resolve(env, disk, windows=True) == r"C:\tools\claude.EXE"


def test_the_path_is_searched_when_the_variable_is_unset_or_blank():
    disk = _posix("/usr/local/bin/claude")
    env = {"PATH": "/usr/bin:/usr/local/bin"}
    assert claude_cli.resolve(env, disk, windows=False) == "/usr/local/bin/claude"
    env[claude_cli.ENV_VAR] = "   "
    assert claude_cli.resolve(env, disk, windows=False) == "/usr/local/bin/claude"


def test_relative_and_empty_path_entries_are_never_probed():
    # "." and "" both mean the current directory, where a document repo could
    # plant its own claude. Only absolute entries count.
    disk = _Disk(r"C:\npm\claude.CMD")
    env = {"PATH": r".;;tools;C:\npm", "PATHEXT": ".COM;.EXE;.BAT;.CMD"}
    assert claude_cli.resolve(env, disk, windows=True) == r"C:\npm\claude.CMD"
    assert disk.probed and all(ntpath.isabs(p) and ntpath.splitdrive(p)[0] for p in disk.probed)
    pdisk = _posix("/bin/claude")
    assert claude_cli.resolve({"PATH": ".::bin:/bin"}, pdisk, windows=False) == "/bin/claude"
    assert all(posixpath.isabs(p) for p in pdisk.probed)


def test_quoted_path_entries_are_unquoted_and_still_must_be_absolute():
    # Windows accepts a PATH entry wrapped in double quotes, which is how an
    # entry with a semicolon is written. A quoted "." is still the current directory.
    disk = _Disk(r"C:\npm\claude.CMD", r".\claude.CMD")
    env = {"PATH": r'".";"C:\npm"', "PATHEXT": ".COM;.EXE;.BAT;.CMD"}
    assert claude_cli.resolve(env, disk, windows=True) == r"C:\npm\claude.CMD"
    assert all(ntpath.splitdrive(p)[0] for p in disk.probed)


def test_claude_exe_later_on_the_path_beats_an_earlier_batch_shim():
    disk = _Disk(r"C:\npm\claude.CMD", r"C:\Users\u\.local\bin\claude.exe")
    env = {"PATH": r"C:\npm;C:\Users\u\.local\bin", "PATHEXT": ".COM;.EXE;.BAT;.CMD"}
    assert claude_cli.resolve(env, disk, windows=True) == r"C:\Users\u\.local\bin\claude.exe"


def test_a_batch_shim_is_the_fallback_and_scripts_are_not_runnable_targets():
    disk = _Disk(r"C:\npm\claude", r"C:\npm\claude.JS", r"C:\npm\claude.CMD")
    env = {"PATH": r"C:\npm", "PATHEXT": ".COM;.EXE;.BAT;.CMD;.JS;.PY"}
    assert claude_cli.resolve(env, disk, windows=True) == r"C:\npm\claude.CMD"


def test_a_missing_cli_is_a_closed_error_naming_the_variable():
    with pytest.raises(claude_cli.ClaudeUnavailable) as info:
        claude_cli.resolve({"PATH": "/usr/bin"}, _posix(), windows=False)
    msg = str(info.value)
    assert claude_cli.ENV_VAR in msg
    assert "installed" in msg and "logged in" in msg
    # The call sites catch RuntimeError, so the error stays closed there too.
    assert isinstance(info.value, RuntimeError)


def test_an_unresolvable_variable_fails_closed_without_echoing_its_value():
    env = {claude_cli.ENV_VAR: "/" + _SECRET, "PATH": "/usr/bin"}
    with pytest.raises(claude_cli.ClaudeUnavailable) as info:
        claude_cli.resolve(env, _posix("/usr/bin/claude"), windows=False)
    assert claude_cli.ENV_VAR in str(info.value)
    assert _SECRET not in str(info.value)


def test_every_call_sends_the_prompt_by_file_with_tools_and_mcp_off(work):
    # A long prompt in argv breaks both limits (about 32K characters for a
    # Windows command line, 128 KiB for one Linux argument), so the prompt
    # always travels in a file. The model gets no built-in tool, no MCP
    # server and no project settings, since the document is untrusted input.
    prompt = "line one\nline two\n" + "x" * 40000
    runner = _Runner(result="done")
    env = {claude_cli.ENV_VAR: "/opt/tools/claude"}
    out = claude_cli.run(prompt, "doc", timeout=5, environ=env,
                         exists=_posix("/opt/tools/claude"), runner=runner,
                         windows=False, tmpdir=work)
    assert out == "done"
    (argv, kwargs), = runner.calls
    assert argv[:3] == ["/opt/tools/claude", "-p", claude_cli.FIXED_PROMPT]
    assert argv[3] == "--append-system-prompt-file"
    assert argv[5:] == _LOCKDOWN_EXPECTED
    assert runner.prompt_file_text == prompt
    assert max(len(a) for a in argv) < 1000
    assert set(kwargs) == {"input", "timeout", "cwd", "env"}
    assert (kwargs["input"], kwargs["timeout"]) == ("doc", 5)
    assert not os.path.exists(argv[4]), "the prompt file outlives the call"


@pytest.mark.parametrize("windows", [False, True])
def test_the_child_runs_in_a_private_empty_folder(work, windows):
    # The CLI reads .claude/settings.json and CLAUDE.md from its working
    # directory, and -p skips the trust prompt. A document folder with a
    # settings file could run hooks. So the child never starts where the caller
    # stands, its folder is empty, and only user settings load.
    cli = r"C:\npm\claude.exe" if windows else "/opt/tools/claude"
    runner = _Runner(result="done")
    claude_cli.run("p", "doc", environ={claude_cli.ENV_VAR: cli}, exists=_Disk(cli),
                   runner=runner, windows=windows, tmpdir=work)
    (argv, kwargs), = runner.calls
    cwd = kwargs["cwd"]
    assert os.path.isabs(cwd)
    assert os.path.normcase(os.path.abspath(cwd)) != os.path.normcase(os.getcwd())
    assert runner.cwd_listing == [], "the child's working folder is not empty"
    assert os.path.dirname(argv[4]) != cwd, "the prompt file sits in the working folder"
    assert argv[argv.index("--setting-sources") + 1] == "user"
    assert os.listdir(work) == [], "the private folder outlives the call"


def test_windows_children_skip_the_current_directory_in_the_exe_search(work, monkeypatch):
    # An npm claude.cmd shim runs "node" by bare name, and cmd.exe looks for it
    # in the current directory before PATH unless this variable is set. An old
    # value under another spelling must not survive next to the new one.
    monkeypatch.setitem(os.environ, "NODEFAULTCURRENTDIRECTORYINEXEPATH", "")
    cli = r"C:\npm\claude.CMD"
    runner = _Runner(result="done")
    claude_cli.run("p", "doc", environ={"PATH": r"C:\npm"}, exists=_Disk(cli),
                   runner=runner, windows=True, tmpdir=work)
    (_, kwargs), = runner.calls
    matches = [v for k, v in kwargs["env"].items()
               if k.lower() == "nodefaultcurrentdirectoryinexepath"]
    assert matches == ["1"]
    assert kwargs["env"].get("PATH") == os.environ.get("PATH"), "the rest of the environment is kept"
    runner = _Runner(result="done")
    claude_cli.run("p", "doc", environ={claude_cli.ENV_VAR: "/opt/claude"},
                   exists=_Disk("/opt/claude"), runner=runner, windows=False, tmpdir=work)
    assert runner.calls[0][1]["env"] is None, "a POSIX child inherits the environment unchanged"


def test_an_unwritable_temp_folder_is_a_closed_error_without_the_path(work):
    missing = os.path.join(work, "missing", _SECRET)
    runner = _Runner(result="done")
    with pytest.raises(claude_cli.ClaudeUnavailable) as info:
        claude_cli.run("p", "t", environ={claude_cli.ENV_VAR: "/opt/claude"},
                       exists=_Disk("/opt/claude"), runner=runner, windows=False,
                       tmpdir=missing)
    assert runner.calls == []
    assert _SECRET not in str(info.value)
    assert "temporary" in str(info.value)


def test_a_start_failure_is_a_closed_error_without_the_path(work):
    err = FileNotFoundError(2, "The system cannot find the file specified", _SECRET)
    runner = _Runner(raises=err)
    with pytest.raises(claude_cli.ClaudeUnavailable) as info:
        claude_cli.run("p", "t", environ={claude_cli.ENV_VAR: "/" + _SECRET},
                       exists=_posix("/" + _SECRET), runner=runner, windows=False,
                       tmpdir=work)
    assert _SECRET not in str(info.value)
    assert claude_cli.ENV_VAR in str(info.value)
    assert os.listdir(work) == [], "the prompt file outlives the start failure"
