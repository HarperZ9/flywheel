"""A Windows batch shim runs under cmd.exe, so what reaches it is checked first.

cmd.exe parses a .cmd or .bat file's arguments a second time. The argument list
holds the CLI path, a fixed line, the prompt file's path and fixed flags, and a
batch call is refused when any of them holds a character cmd.exe would read as
a command. No test here starts a process.
"""
import os

import pytest

from articulate import claude_cli
from cli_fakes import (_CMD_UNSAFE_EXPECTED, _CMD_UNSAFE_UNQUOTED_EXPECTED, _Disk,  # noqa: F401
                       _Runner, work)


def test_the_unsafe_sets_match_the_hand_written_ones():
    # A pin only. The process tests run each character through cmd.exe.
    assert claude_cli.CMD_UNSAFE == _CMD_UNSAFE_EXPECTED
    assert claude_cli.CMD_UNSAFE_UNQUOTED == _CMD_UNSAFE_UNQUOTED_EXPECTED


@pytest.mark.parametrize("suffix", [".cmd", ".CMD", ".bat", ".Bat"])
def test_batch_suffixes_are_recognised(suffix):
    assert claude_cli.is_batch(r"C:\npm\claude" + suffix, windows=True)
    assert not claude_cli.is_batch(r"C:\npm\claude" + suffix, windows=False)
    assert not claude_cli.is_batch(r"C:\npm\claude.exe", windows=True)


def test_a_batch_shim_gets_a_fixed_argv(work):
    # cmd.exe re-parses a .cmd file's arguments and cuts one at its first
    # newline, so nothing from the prompt may travel in argv.
    prompt = 'first line\nsecond "line" with %PATH% & ^ | < > !'
    runner = _Runner(result="done")
    claude_cli.run(prompt, "doc", environ={"PATH": r"C:\npm"},
                   exists=_Disk(r"C:\npm\claude.CMD"), runner=runner, windows=True,
                   tmpdir=work)
    (argv, _), = runner.calls
    assert argv[0] == r"C:\npm\claude.CMD"
    assert runner.prompt_file_text == prompt
    assert not any(set(a) & _CMD_UNSAFE_EXPECTED for a in argv[1:])


@pytest.mark.parametrize("suffix", [".cmd", ".bat"])
@pytest.mark.parametrize("char", sorted(_CMD_UNSAFE_EXPECTED))
def test_a_batch_shim_with_an_unsafe_path_fails_closed(work, suffix, char):
    runner = _Runner(result="done")
    cli = "C:\\a" + char + "b\\claude" + suffix
    with pytest.raises(claude_cli.ClaudeUnavailable) as info:
        claude_cli.run("p", "t", environ={claude_cli.ENV_VAR: cli}, exists=_Disk(cli),
                       runner=runner, windows=True, tmpdir=work)
    assert runner.calls == []
    assert claude_cli.ENV_VAR in str(info.value)
    assert os.listdir(work) == [], "the prompt file outlives the refusal"


@pytest.mark.parametrize("char", sorted(_CMD_UNSAFE_EXPECTED | _CMD_UNSAFE_UNQUOTED_EXPECTED))
def test_a_batch_call_refuses_an_unsafe_temp_folder(work, char):
    # TEMP=C:\Users\A&B\... has no space, so Python passes the prompt path
    # unquoted and cmd.exe splits the command at "&".
    tmp = os.path.join(work, "a" + char + "b")
    try:
        os.mkdir(tmp)
    except (OSError, ValueError):
        pytest.skip(f"this file system cannot name a folder with {char!r}")
    runner = _Runner(result="done")
    with pytest.raises(claude_cli.ClaudeUnavailable):
        claude_cli.run("p", "t", environ={"PATH": r"C:\npm"},
                       exists=_Disk(r"C:\npm\claude.CMD"), runner=runner,
                       windows=True, tmpdir=tmp)
    assert runner.calls == []
    assert os.listdir(tmp) == [], "the private folder outlives the refusal"


def test_a_paren_is_refused_only_where_cmd_would_see_it_unquoted(work):
    # Python quotes an argument that holds a space, and inside quotes cmd.exe
    # reads ")" as text. So an npm prefix under "Program Files (x86)" still runs.
    ok = r"C:\Program Files (x86)\npm\claude.cmd"
    runner = _Runner(result="done")
    claude_cli.run("p", "t", environ={claude_cli.ENV_VAR: ok}, exists=_Disk(ok),
                   runner=runner, windows=True, tmpdir=work)
    assert runner.calls
    bad = r"C:\a)b\claude.cmd"
    with pytest.raises(claude_cli.ClaudeUnavailable):
        claude_cli.run("p", "t", environ={claude_cli.ENV_VAR: bad}, exists=_Disk(bad),
                       runner=_Runner(result="done"), windows=True, tmpdir=work)
