"""Each MCP tool Articulate lists declares a title and explicit behavior hints,
and no tool description claims more than the tool does.

A host reads readOnlyHint and destructiveHint to decide which calls need the
user's approval, and Claude's directory review requires a title and the hints
that apply on every tool. The MCP defaults are the unsafe reading
(readOnlyHint false, destructiveHint true, openWorldHint true), so a tool that
leaves a hint out is described wrongly, and every tool here sets all four.

The description checks tie words to behavior. A tool marked local must say so
and must not say it sends the text anywhere. A tool that reaches a hosted model
must say where the text goes, in its description and its title. A tool that
returns rewritten text must say it edits none of the user's files. No title or
description may claim a guarantee, a proof, or knowledge of who or what wrote a
text. A planted overclaim for each rule shows the check can fail.

The behavior behind the local hint (no socket, no process, no file) is tested in
test_local_tools_stay_local.py.
"""
import importlib.util
import json
import pathlib
import re
import subprocess
import sys

import pytest

from articulate import local_mcp
from articulate.tool_text import LIMIT

HINTS = ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")

# Tools whose result carries rewritten text. Their names read like file edits.
REWRITES = {"fix", "polish", "edit_plan", "edit_submit"}
# Tools whose result is a set of findings; their description carries the
# authorship limit.
FINDINGS = {"check", "score"}

OVERCLAIM = re.compile(
    r"(?i)\bguarantee|\bprove[sn]?\b|\bproof\b|\b100 ?%|\bperfect(?:ly)?\b|\bflawless"
    r"|\bcertif(?:y|ies|ied)\b|\bfully accurate\b|\balways (?:right|correct|accurate)\b"
    r"|\bnever (?:wrong|misses|fails)\b|\bevery (?:error|mistake|problem)\b"
    r"|\bany language\b|\bstate[- ]of[- ]the[- ]art\b|\bbest[- ]in[- ]class\b"
    r"|\bworld[- ]class\b|\bundetectable\b|\bbypass|\bevad(?:e|es|ing)\b|\bhumani[sz]"
    r"|\bhuman[- ](?:written|authored)\b|\bai[- ](?:generated|written|authored|detect)"
    r"|\bdetects? ai\b|\bauthorship\b|\bwho (?:or what )?wrote\b")
LOCAL_WORDS = re.compile(r"(?i)\blocal\b|\bno network\b|\bnetwork-free\b|\bon your machine\b")
SENDS = re.compile(r"(?i)\bsends?\b|\bhosted\b|\buploads?\b")
WRITES_A_FILE = re.compile(
    r"(?i)\b(?:writes?|saves?|edits?|modif(?:y|ies)|overwrites?|deletes?) "
    r"(?:the|your|a) (?:file|document)")


def _listed(monkeypatch, tool_set):
    if tool_set is None:
        monkeypatch.delenv("ARTICULATE_MCP_TOOLS", raising=False)
    else:
        monkeypatch.setenv("ARTICULATE_MCP_TOOLS", tool_set)
    response = local_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    return response["result"]["tools"]


def _overclaims(name, title, description, hints):
    """Every way this tool's words claim more than its hints say it does."""
    problems = []
    # The limit line is the vetted statement that a finding says nothing about
    # authorship; it is scanned for presence, never as a claim.
    body = description.replace(LIMIT, "")
    for text, where in ((title, "title"), (body, "description")):
        found = OVERCLAIM.search(text)
        if found:
            problems.append(f"{name}: {where} overclaims with {found.group(0)!r}")
    if hints["openWorldHint"]:
        if "hosted model" not in body:
            problems.append(f"{name}: reaches a hosted model and does not say so")
        if "hosted" not in title:
            problems.append(f"{name}: title hides that the text goes to a hosted model")
    else:
        if not LOCAL_WORDS.search(body):
            problems.append(f"{name}: a local tool that does not say it runs locally")
        if SENDS.search(body) or SENDS.search(title):
            problems.append(f"{name}: a local tool whose words say it sends the text")
    if hints["readOnlyHint"] and WRITES_A_FILE.search(body):
        problems.append(f"{name}: marked read-only and says it writes a file")
    if name in REWRITES and "edits none of your files" not in body:
        problems.append(f"{name}: returns a rewrite and does not say it edits no file")
    if name in FINDINGS and LIMIT not in description:
        problems.append(f"{name}: returns findings without the authorship limit")
    return problems


@pytest.mark.parametrize("tool_set", [None, "local"])
def test_every_listed_tool_has_a_title_and_every_hint(monkeypatch, tool_set):
    tools = _listed(monkeypatch, tool_set)
    assert tools, "tools/list returned no tools"
    for tool in tools:
        name = tool["name"]
        title = tool.get("title")
        assert isinstance(title, str) and title.strip(), f"{name} has no title"
        annotations = tool.get("annotations")
        assert isinstance(annotations, dict), f"{name} has no annotations"
        assert annotations.get("title") == title, f"{name}: two different titles"
        for hint in HINTS:
            assert type(annotations.get(hint)) is bool, (
                f"{name} leaves {hint} to the protocol default")


def test_the_hints_say_what_each_tool_does(monkeypatch):
    hosted = {"judge", "fix", "polish"}
    for tool in _listed(monkeypatch, None):
        hints = {h: tool["annotations"][h] for h in HINTS}
        if tool["name"] in hosted:
            # The text leaves the machine and spends the user's quota, so the
            # host asks before each call; nothing on disk is changed or removed.
            assert hints == {"readOnlyHint": False, "destructiveHint": False,
                             "idempotentHint": False, "openWorldHint": True}, tool["name"]
        else:
            assert hints == {"readOnlyHint": True, "destructiveHint": False,
                             "idempotentHint": True, "openWorldHint": False}, tool["name"]


@pytest.mark.parametrize("tool_set", [None, "local"])
def test_no_title_or_description_claims_more_than_the_tool_does(monkeypatch, tool_set):
    problems = []
    for tool in _listed(monkeypatch, tool_set):
        hints = {h: tool["annotations"][h] for h in HINTS}
        problems += _overclaims(tool["name"], tool["title"], tool["description"], hints)
    assert not problems, "\n".join(problems)


_LOCAL = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True,
          "openWorldHint": False}
_HOSTED = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False,
           "openWorldHint": True}
_OK_LOCAL = "Checks a passage. Runs on your machine. " + LIMIT


@pytest.mark.parametrize("name,title,description,hints,expected", [
    ("check", "Check prose", "Guarantees every error is caught. Local. " + LIMIT,
     _LOCAL, "overclaims"),
    ("check", "Check prose", "Tells you who wrote the text. Local. " + LIMIT,
     _LOCAL, "overclaims"),
    ("check", "Perfect prose checker", _OK_LOCAL, _LOCAL, "title overclaims"),
    ("check", "Check prose", "Sends the text for a second read. Local. " + LIMIT,
     _LOCAL, "say it sends"),
    ("check", "Check prose", "Checks a passage. " + LIMIT, _LOCAL,
     "does not say it runs locally"),
    ("check", "Check prose", "Checks a passage. Runs on your machine.", _LOCAL,
     "authorship limit"),
    ("score", "Score prose", "Scores a passage and saves the file. Local. " + LIMIT,
     _LOCAL, "writes a file"),
    ("judge", "Editor read through a hosted model", "Reads the passage.", _HOSTED,
     "does not say so"),
    ("judge", "Editor read", "Reads the passage through a hosted model.", _HOSTED,
     "title hides"),
    ("fix", "Suggest a rewrite through a hosted model",
     "Rewrites the passage through a hosted model.", _HOSTED, "edits no file"),
], ids=["guarantee", "who-wrote", "title-perfect", "local-says-sends", "no-local-word",
        "no-authorship-limit", "read-only-saves", "hosted-unnamed", "hosted-title",
        "rewrite-no-file-line"])
def test_the_overclaim_check_can_fail(name, title, description, hints, expected):
    """Control: each rule above rejects a description written to break it, so a
    clean result on the real tools is a finding and not a check that never fires."""
    problems = _overclaims(name, title, description, hints)
    assert any(expected in p for p in problems), problems


def test_a_clean_planted_description_passes():
    """Control in the other direction: the rules accept a description that states
    only what the tool does, so they do not fail every input."""
    assert _overclaims("check", "Check prose", _OK_LOCAL, _LOCAL) == []


# Runs in a child process: importing fastmcp here would leave it in sys.modules,
# and test_local_mcp checks that the stdio server never pulls it in.
_FASTMCP_LISTING = """
import asyncio, json, sys
sys.path.insert(0, sys.argv[1])
import fastmcp
from articulate import mcp_server

async def main():
    async with fastmcp.Client(mcp_server.build_server()) as client:
        tools = await client.list_tools()
    print(json.dumps([{"name": t.name, "title": t.title, "description": t.description,
                       "annotations": t.annotations.model_dump() if t.annotations else None}
                      for t in tools]))

asyncio.run(main())
"""


@pytest.mark.parametrize("tool_set", [None, "local"])
def test_the_fastmcp_server_declares_the_same_titles_and_hints(monkeypatch, tool_set):
    if importlib.util.find_spec("fastmcp") is None:
        pytest.skip("fastmcp is not installed (the [mcp] extra)")
    stdio = {t["name"]: t for t in _listed(monkeypatch, tool_set)}
    src = str(pathlib.Path(local_mcp.__file__).resolve().parents[1])
    run = subprocess.run([sys.executable, "-c", _FASTMCP_LISTING, src],
                         capture_output=True, text=True, timeout=180)
    assert run.returncode == 0, run.stderr[-2000:]
    tools = json.loads(run.stdout)
    assert tools, "the fastmcp server listed no tools"
    problems = []
    for tool in tools:
        want = stdio[tool["name"]]
        annotations = tool["annotations"]
        assert tool["title"] == want["title"], tool["name"]
        assert annotations is not None, f"{tool['name']} has no annotations"
        assert annotations["title"] == want["title"], tool["name"]
        got = {h: annotations[h] for h in HINTS}
        assert got == {h: want["annotations"][h] for h in HINTS}, tool["name"]
        problems += _overclaims(tool["name"], tool["title"], tool["description"] or "", got)
    assert not problems, "\n".join(problems)


def test_the_table_module_prose_passes_the_readme_profile():
    """tool_meta.py joins the modules whose docstrings and comments the project
    holds to its own house style (test_dogfood.py covers the others)."""
    import articulate
    from articulate import profiles, pysource
    path = pathlib.Path(articulate.__file__).parent / "tool_meta.py"
    result = articulate.check_text(pysource.prose_of(path.read_text(encoding="utf-8")),
                                   profile=profiles.load("readme"))
    assert result["gate"] == "ok", [f["match"] for f in result["high"] + result["medium"]]


_FASTMCP_LOCAL_CALLS = """
import asyncio, json, sys
sys.path.insert(0, sys.argv[1])
import fastmcp
from articulate import backends, mcp_server

def forbidden(*args, **kwargs):
    raise AssertionError('local tools reached backend resolution')
backends.complete = forbidden

async def main():
    async with fastmcp.Client(mcp_server.build_server()) as client:
        for name in ('fix', 'judge', 'polish'):
            for backend in ('auto', 'host', 'none', 'sampling', 'ollama', 'openai', 'anthropic', 'claude-cli'):
                response = await client.call_tool(name, {'text': 'We wait.', 'backend': backend})
                value = json.loads(response.content[0].text)
                if backend in ('auto', 'host', 'none'):
                    assert value['ok'] is True, value
                    assert value['backend'] == ('none' if backend == 'none' else 'host'), value
                else:
                    assert value['ok'] is False and 'local-only' in value['note'], value
        response = await client.call_tool('edit_plan', {'text': 'We wait.'})
        plan = json.loads(response.content[0].text)
        response = await client.call_tool('edit_submit', {'text': 'We wait.', 'rewrite': 'We pause.', 'plan_id': plan['plan_id']})
        value = json.loads(response.content[0].text)
        assert value['receipt']['backend'] == 'host' and value['text'] == 'We pause.', value
    print('local calls passed')

asyncio.run(main())
"""


def test_fastmcp_local_calls_never_resolve_a_backend(monkeypatch):
    if importlib.util.find_spec("fastmcp") is None:
        pytest.skip("fastmcp is not installed (the [mcp] extra)")
    monkeypatch.setenv("ARTICULATE_MCP_TOOLS", "local")
    monkeypatch.setenv("ARTICULATE_LOCAL_ONLY", "1")
    src = str(pathlib.Path(local_mcp.__file__).resolve().parents[1])
    run = subprocess.run([sys.executable, "-c", _FASTMCP_LOCAL_CALLS, src],
                         capture_output=True, text=True, timeout=180)
    assert run.returncode == 0, run.stderr[-3000:]
    assert run.stdout.strip() == "local calls passed"
