"""The tools marked local read the text they are given and nothing else.

tool_meta marks them readOnlyHint true and openWorldHint false, and the Claude
plugin's privacy policy says they open no network connection, start no other
program, open none of the user's files and write nothing. The module-state scan
below checks for retained module-level copies; it does not inspect transient
transport or session memory. This file runs every tool the server lists as local, through the same
JSON-RPC entry point a host uses, with each of those actions made to fail. The
tool set comes from the listing's own hints, so a new tool marked local is held
to the same rules the moment it is listed.

Each guard also records the attempt, because a tool body that catches every
exception would turn a blocked write into an ordinary error result. The hosted
tools run under the same guards with the local-only switch on, which is where a
user lands who lists them in the plugin: they must refuse before writing the
text anywhere.

Each guard has a control below that trips it on purpose, so a clean run is a
finding about the tools and not a guard that never fires.
"""
import builtins
import io
import json
import os
import pathlib
import socket
import subprocess
import sys

import pytest

import articulate
from articulate import local_mcp, mcp_server

PKG = pathlib.Path(articulate.__file__).resolve().parent
MARKER = "Zebracorn quartermaster 7319 leveraged a cutting-edge synergy."

PLUGIN_ENV = {"ARTICULATE_MCP_TOOLS": "local", "ARTICULATE_LOCAL_ONLY": "1"}
# Every blocked attempt, recorded before the guard raises.
ESCAPES = []


class Escaped(AssertionError):
    """A local tool reached for the network, a process or a file."""


def _refuse(what):
    def refuse(*args, **kwargs):
        ESCAPES.append(f"{what}: {args[:2]!r}")
        raise Escaped(f"a local tool tried to {what}: {args[:2]!r}")
    return refuse


def _voice_store():
    """The one folder outside the package a local tool may read: the voice store,
    where voice_compare reads a profile the author saved with the CLI."""
    from articulate import voice_store
    return voice_store.store_dir().resolve()


def _house_config():
    """The house-voice settings folder, which house_brief and house_transform
    read (never write) to learn whether the user turned the voice off or tuned it."""
    from articulate import house_settings
    return house_settings.config_dir().resolve()


def _package_read_only(real):
    """open() limited to reading the package's own files, which is how Python
    loads a module imported inside a function, the voice store and the house
    settings folder."""
    store, config = _voice_store(), _house_config()

    def opener(file, mode="r", *args, **kwargs):
        if isinstance(file, (str, bytes, os.PathLike)):
            path = pathlib.Path(os.fsdecode(file)).resolve()
            readable = PKG in path.parents or store in path.parents or config in path.parents
            if readable and not set(mode) & set("wax+"):
                return real(file, mode, *args, **kwargs)
        ESCAPES.append(f"open {file!r} in mode {mode!r}")
        raise Escaped(f"a local tool tried to open {file!r} in mode {mode!r}")
    return opener


@pytest.fixture
def voice_dir(monkeypatch, tmp_path_factory):
    """A saved profile for voice_compare, written before the seal goes on."""
    from articulate import voice, voice_identity, voice_store
    folder = tmp_path_factory.mktemp("voice")
    voice_identity.ensure_identity(folder)
    profile = voice.build_profile([MARKER + " The rain came in March and we left."])
    voice_store.save(voice_identity.bind(profile, folder), "sealed", folder)
    monkeypatch.setenv("ARTICULATE_VOICE_DIR", str(folder))
    config = tmp_path_factory.mktemp("config")
    (config / "house.json").write_text('{"mode": "default"}', encoding="utf-8")
    monkeypatch.setenv("ARTICULATE_CONFIG_DIR", str(config))
    return folder


@pytest.fixture
def sealed(monkeypatch, tmp_path, voice_dir):
    """No socket, no process, no file outside the package, and an empty working
    folder to show that nothing landed in it."""
    ESCAPES.clear()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(socket, "socket", _refuse("open a socket"))
    monkeypatch.setattr(socket, "create_connection", _refuse("open a connection"))
    monkeypatch.setattr(socket, "getaddrinfo", _refuse("resolve a host name"))
    monkeypatch.setattr(subprocess, "Popen", _refuse("start a process"))
    monkeypatch.setattr(os, "system", _refuse("run a shell command"))
    for name in ("execv", "execve", "spawnv", "spawnve", "startfile", "fork"):
        if hasattr(os, name):
            monkeypatch.setattr(os, name, _refuse(f"call os.{name}"))
    real_open = builtins.open
    monkeypatch.setattr(builtins, "open", _package_read_only(real_open))
    monkeypatch.setattr(io, "open", _package_read_only(real_open))
    # Older pathlib versions cache their opener, bypassing patches to io.open.
    # Guard the public Path entrypoint as well, with the same package-read rule.
    monkeypatch.setattr(pathlib.Path, "open", _package_read_only(real_open))
    monkeypatch.setattr(os, "open", _refuse("open a file descriptor"))
    return tmp_path


def _local_tools(environ):
    tools = local_mcp.listed_tools(environ)
    return [t for t in tools if t["annotations"]["openWorldHint"] is False]


def _arguments(tool):
    """A valid call: the marker text for every required string argument."""
    schema = tool["inputSchema"]
    args = {name: MARKER for name in schema.get("required", [])
            if schema["properties"][name].get("type") == "string"}
    if tool["name"] == "edit_submit":
        args["plan_id"] = mcp_server.do_edit_plan(MARKER)["plan_id"]
    if tool["name"] == "corpus_check":
        args["documents"] = [{"name": "a.md", "text": MARKER}, {"name": "b.md", "text": MARKER}]
    if tool["name"] == "title_workshop":
        args["titles"] = [MARKER, MARKER]
    if tool["name"] in ("voice_compare", "voice_apply_plan"):
        args["voice_name"] = "sealed"
    if tool["name"] == "voice_apply_plan":
        args["authored_by_user"] = True
    return args


def _call(tool):
    response = local_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                 "params": {"name": tool["name"],
                                            "arguments": _arguments(tool)}})
    return response["result"]


@pytest.mark.parametrize("environ", [PLUGIN_ENV, {}], ids=["plugin", "default"])
def test_every_local_tool_runs_sealed(monkeypatch, sealed, environ):
    for name in ("ARTICULATE_MCP_TOOLS", "ARTICULATE_LOCAL_ONLY"):
        monkeypatch.delenv(name, raising=False)
    for name, value in environ.items():
        monkeypatch.setenv(name, value)
    tools = _local_tools(environ)
    assert {t["name"] for t in tools} >= {"check", "score", "articulate.status",
                                           "articulate.doctor"}
    for tool in tools:
        result = _call(tool)
        assert not result.get("isError"), (tool["name"], result)
        json.loads(result["content"][0]["text"])
    assert ESCAPES == []
    assert list(sealed.iterdir()) == [], "a local tool wrote into the working folder"


@pytest.mark.parametrize("body", ["do_judge", "do_fix", "do_polish"])
def test_editor_bodies_under_local_only_touch_nothing(monkeypatch, sealed, body):
    monkeypatch.setenv("ARTICULATE_LOCAL_ONLY", "1")
    result = getattr(mcp_server, body)(MARKER)
    assert result["ok"] is True and result["backend"] == "host", result
    assert ESCAPES == []


@pytest.mark.parametrize("body", ["do_judge", "do_fix", "do_polish"])
@pytest.mark.parametrize("backend", ["sampling", "anthropic", "claude-cli", "openai", "ollama"])
def test_explicit_connections_refuse_without_touching_anything(monkeypatch, sealed, body, backend):
    monkeypatch.setenv("ARTICULATE_LOCAL_ONLY", "1")
    result = getattr(mcp_server, body)(MARKER, backend=backend)
    assert result["ok"] is False and "local-only" in result["note"], result
    assert ESCAPES == []


def _strings(value, depth=0):
    if isinstance(value, str):
        yield value
    elif depth < 4 and isinstance(value, dict):
        for item in list(value.values()):
            yield from _strings(item, depth + 1)
    elif depth < 4 and isinstance(value, (list, tuple, set, frozenset)):
        for item in list(value):
            yield from _strings(item, depth + 1)


def test_no_module_level_copy_of_the_text_remains_after_calls(monkeypatch, sealed):
    for name, value in PLUGIN_ENV.items():
        monkeypatch.setenv(name, value)
    for tool in _local_tools(PLUGIN_ENV):
        _call(tool)
    kept = [name for name, module in list(sys.modules.items())
            if name == "articulate" or name.startswith("articulate.")
            for text in _strings(vars(module)) if "Zebracorn" in text]
    assert not kept, f"module state holds the checked text: {sorted(set(kept))}"


def test_the_plugin_tool_set_lists_only_local_tools():
    listed = {t["name"] for t in local_mcp.listed_tools(PLUGIN_ENV)}
    local = {t["name"] for t in _local_tools(PLUGIN_ENV)}
    assert listed == local, "the plugin lists a tool that is not marked local"


@pytest.mark.parametrize("attempt", [
    lambda tmp: socket.socket(),
    lambda tmp: socket.create_connection(("example.com", 443)),
    lambda tmp: subprocess.run([sys.executable, "--version"]),
    lambda tmp: open(tmp / "leak.txt", "w"),
    lambda tmp: pathlib.Path(tmp / "leak.txt").write_text("x"),
    lambda tmp: pathlib.Path(tmp / "leak.bin").write_bytes(b"x"),
    lambda tmp: pathlib.Path(tmp / "leak.txt").open("w"),
    lambda tmp: pathlib.Path.home().joinpath("notes.md").read_text(),
    lambda tmp: open(pathlib.Path.home() / "notes.md"),
    lambda tmp: os.open(str(tmp / "leak.txt"), os.O_WRONLY | os.O_CREAT),
    lambda tmp: open(_voice_store() / "leak.json", "w"),
    lambda tmp: (_voice_store() / "sealed.json").write_text("{}"),
    lambda tmp: open(_house_config() / "house.json", "w"),
], ids=["socket", "connect", "process", "open-write", "path-write", "path-write-bytes",
        "path-open", "path-read-user-file", "read-user-file", "os-open",
        "voice-store-write", "voice-store-overwrite", "house-config-write"])
def test_each_guard_trips(sealed, attempt):
    """Control: every escape the sealed fixture claims to block is blocked and
    recorded."""
    with pytest.raises(Escaped):
        attempt(sealed)
    assert len(ESCAPES) == 1


def test_a_swallowed_escape_is_still_recorded(sealed):
    """Control: a body that catches the guard's error still fails the record."""
    try:
        open(sealed / "leak.txt", "w")
    except Exception:  # noqa: BLE001 - the shape of a tool body's catch-all
        pass
    assert ESCAPES


def test_the_text_scan_finds_a_planted_copy(monkeypatch):
    """Control: the module-state scan finds the marker when a module does keep it."""
    from articulate import tool_meta
    monkeypatch.setattr(tool_meta, "_PLANTED", {"kept": [MARKER]}, raising=False)
    assert any("Zebracorn" in s for s in _strings(vars(tool_meta)))


def test_the_voice_store_is_readable_under_the_seal(sealed, voice_dir):
    """Control for the one allowance: a read of a saved profile works and records
    no escape, so the write controls above are about the mode and not the path."""
    with open(voice_dir / "sealed.json", encoding="utf-8") as fh:
        assert json.load(fh)["schema"] == "articulate/voice-profile/v1"
    assert ESCAPES == []


def test_the_house_settings_are_readable_under_the_seal(sealed):
    """Control for the second allowance: reading the settings file records no escape."""
    with open(_house_config() / "house.json", encoding="utf-8") as fh:
        assert json.load(fh)["mode"] == "default"
    assert ESCAPES == []
