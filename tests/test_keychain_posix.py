"""Falsifiers for the macOS and Linux credential stores. The subprocess call
is replaced in every test: these backends were not run on their platforms,
and this file only proves the commands, the stdin handling and the refusals."""
import subprocess

import pytest

from harness import keychain, keychain_posix
from harness.code_session import mcp_oauth

KEY = "sk-" + "ant-" + "p" * 40
JSON_TOKEN = '{"access_token": "' + "t" * 24 + '", "note": "it\'s \\\\ here"}'


class FakeTool:
    """Stands in for `security` or `secret-tool`: keeps items in a dict and
    records every argv and stdin it was given."""

    def __init__(self, fail_writes=False):
        self.items, self.calls, self.fail_writes = {}, [], fail_writes

    def __call__(self, argv, input=None, capture_output=True, text=True,  # noqa: A002
                 timeout=None, check=False):
        self.calls.append((list(argv), input))
        code, out = self._security(argv, input) if argv[0] == "security" \
            else self._secret_tool(argv, input)
        return subprocess.CompletedProcess(argv, code, stdout=out, stderr="")

    def _security(self, argv, stdin):
        if argv[1] == "-i":
            words = stdin.strip().split(" ")
            if not self.fail_writes:
                self.items[words[words.index("-a") + 1]] = words[words.index("-w") + 1]
            return 0, ""                       # exits 0 even when the line failed
        name = argv[argv.index("-a") + 1]
        if argv[1] == "find-generic-password":
            return (0, self.items[name] + "\n") if name in self.items else (44, "")
        return (0, "") if self.items.pop(name, None) is not None else (44, "")

    def _secret_tool(self, argv, stdin):
        name = argv[-1]
        if argv[1] == "store":
            if self.fail_writes:
                return 1, ""
            self.items[name] = stdin
            return 0, ""
        if argv[1] == "lookup":
            return (0, self.items[name]) if name in self.items else (1, "")
        self.items.pop(name, None)
        return 0, ""


@pytest.mark.parametrize("platform,tool", [("darwin", "security"), ("linux", "secret-tool")])
def test_round_trip_and_the_secret_never_rides_on_a_command_line(platform, tool):
    fake = FakeTool()
    assert keychain_posix.write("OPENAI_API_KEY", KEY, platform, fake) == {
        "stored": "OPENAI_API_KEY"}
    assert keychain_posix.read("OPENAI_API_KEY", platform, fake) == KEY
    assert keychain_posix.remove("OPENAI_API_KEY", platform, fake) == {
        "deleted": "OPENAI_API_KEY"}
    assert keychain_posix.read("OPENAI_API_KEY", platform, fake) is None
    assert "error" in keychain_posix.remove("OPENAI_API_KEY", platform, fake)
    assert all(argv[0] == tool for argv, _ in fake.calls)
    assert not any(KEY in part for argv, _ in fake.calls for part in argv)
    assert sum(1 for _, stdin in fake.calls if stdin and KEY in stdin) == 1


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_a_secret_with_quotes_and_spaces_survives(platform):
    fake = FakeTool()
    assert "stored" in keychain_posix.write("MCP_OAUTH_BOARD", JSON_TOKEN, platform, fake)
    assert keychain_posix.read("MCP_OAUTH_BOARD", platform, fake) == JSON_TOKEN
    if platform == "darwin":
        line = fake.calls[0][1]
        assert line.count("\n") == 1 and '"' not in line and "fwb64:" in line


def test_macos_reads_the_write_back_because_interactive_mode_exits_zero():
    result = keychain_posix.write("OPENAI_API_KEY", KEY, "darwin", FakeTool(fail_writes=True))
    assert "did not read back" in result["error"] and KEY not in result["error"]


def test_linux_write_failure_is_reported_with_the_exit_code():
    result = keychain_posix.write("OPENAI_API_KEY", KEY, "linux", FakeTool(fail_writes=True))
    assert "`secret-tool` exit 1" in result["error"] and KEY not in result["error"]


def test_a_tool_that_cannot_start_is_an_error_without_its_arguments():
    def broken(argv, **kwargs):
        raise FileNotFoundError(f"cannot run {argv} with {kwargs.get('input')}")
    result = keychain_posix.write("OPENAI_API_KEY", KEY, "linux", broken)
    assert result == {"error": "`secret-tool` could not be run (FileNotFoundError)"}
    assert keychain_posix.read("OPENAI_API_KEY", "linux", broken) is None


@pytest.mark.parametrize("platform,tool", [("darwin", "security"), ("linux", "secret-tool")])
def test_a_missing_tool_is_refused_by_name(platform, tool):
    assert not keychain_posix.available(platform, which=lambda name: None)
    text = keychain_posix.refusal(platform, which=lambda name: None)
    assert f"`{tool}` command" in text and "not found" in text
    assert keychain_posix.refusal(platform, which=lambda name: "/usr/bin/" + name) == ""


def test_an_unsupported_platform_has_no_store():
    assert keychain_posix.tool_name("freebsd14") is None
    assert not keychain_posix.available("freebsd14")
    assert "error" in keychain_posix.write("X", KEY, "freebsd14")


def test_keychain_routes_to_the_system_tool_off_windows(monkeypatch):
    seen = {}
    monkeypatch.setattr(keychain, "_IS_WINDOWS", False)
    monkeypatch.setattr(keychain_posix, "available", lambda: True)
    monkeypatch.setattr(keychain_posix, "write",
                        lambda name, secret: seen.update({name: secret}) or {"stored": name})
    monkeypatch.setattr(keychain_posix, "remove", lambda name: {"deleted": name})
    assert keychain.keychain_available()
    assert keychain.keychain_set("GEMINI_API_KEY", KEY) == {"stored": "GEMINI_API_KEY"}
    assert seen == {"GEMINI_API_KEY": KEY}
    assert keychain.keychain_delete("GEMINI_API_KEY") == {"deleted": "GEMINI_API_KEY"}


def test_without_the_tool_nothing_is_stored_and_the_tool_is_named(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(keychain, "_IS_WINDOWS", False)
    monkeypatch.setattr(keychain_posix, "available", lambda: False)
    real = keychain_posix.refusal
    monkeypatch.setattr(keychain_posix, "refusal",
                        lambda: real("linux", which=lambda name: None))
    assert not keychain.keychain_available()
    result = keychain.keychain_set("GEMINI_API_KEY", KEY)
    assert "secret-tool" in result["error"] and "environment variable" in result["error"]
    from harness import setup_cli
    ok, message = setup_cli.store("gemini", read_secret=lambda prompt: KEY)
    assert not ok and "secret-tool" in message and "GEMINI_API_KEY" in message
    assert list(tmp_path.iterdir()) == [], "no file fallback for a provider key"


def test_mcp_token_falls_to_the_owner_only_file_when_the_store_refuses(monkeypatch, tmp_path):
    monkeypatch.setattr(keychain, "keychain_available", lambda: True)
    monkeypatch.setattr(keychain, "keychain_set",
                        lambda name, secret: {"error": "credential store write failed"})
    where = mcp_oauth.save_token(str(tmp_path), "board", {"access_token": "t" * 24})
    assert where.endswith("board.json") and where != "the OS credential store"
    assert mcp_oauth.load_token(str(tmp_path), "board") == {"access_token": "t" * 24}
