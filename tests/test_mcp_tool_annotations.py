"""Every MCP tool Flywheel serves carries a title, explicit hints, and a
description that claims no more than the tool does.

Claude and other clients read `readOnlyHint` and `destructiveHint` to decide
whether a call needs the person's confirmation, and a missing hint falls back
to the MCP defaults (`readOnlyHint: false`, `destructiveHint: true`), which
describe no Flywheel tool accurately. A directory reviewer also rejects a tool
without a title or its applicable hints. So the rule is enforced here, over
every server the harness package serves, found by what it answers rather than
by a hand-kept list that a new server could miss.

The description rules are a floor, and a heuristic one: they catch absolute
claims ("guarantees", "proves that"), wording that tells a model to call a
tool unprompted, and a verification claim with no stated limit beside it.
Passing them does not show a description is accurate. The hint-versus-effect
and read-only-writes-nothing tests below are what tie the hints to behavior.
"""
from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

from harness import lane_tool_policy_agents as agents_policy

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "harness"
HINTS = ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")
NAME_RX = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
KNOWN_SERVERS = {"harness.writing_lint.mcp", "harness.writing_mcp",
                 "harness.local_mcp"}

OVERCLAIMS = (
    r"\bguarantee[sd]?\b", r"\balways (?:correct|right|accurate|safe)\b",
    r"\bnever (?:wrong|fails?)\b", r"\b100 ?%", r"\bfool-?proof\b",
    r"\binfallib", r"\btamper-?proof\b", r"\bbullet-?proof\b",
    r"\bproves? (?:that|the answer|correctness)\b", r"\bcertif(?:y|ies|ied)\b",
    r"\b(?:fully|completely|totally) (?:secure|safe|accurate|verified|correct)\b",
    r"\bensures? (?:correctness|accuracy|safety|compliance)\b",
)
# Wording that asks a model to call a tool the person did not ask for.
COERCIONS = (
    r"\b(?:always|first) (?:call|use|run)\b", r"\bbefore assuming\b",
    r"\bcall this tool (?:first|before)\b", r"\byou must\b",
    r"\bwhenever you\b",
)
VERIFY_WORDS = re.compile(r"\b(?:verif\w*|confirm\w*|prov(?:e|es|en|ing)|"
                          r"validat\w*)\b", re.I)
BOUNDS = re.compile(r"\b(?:does not|do not|cannot|never|not (?:show|prove|judge))\b",
                    re.I)

# Lane effects that change something, and effects that reach past the machine.
WRITE_EFFECTS = {"state_write", "outside_write", "publish", "actuate", "spend",
                 "approve", "model_call"}
OPEN_EFFECTS = {"network_read", "model_call", "publish", "spend"}


def problems(tool: dict) -> list[str]:
    """What a directory reviewer or a client would find wrong with one tool."""
    out: list[str] = []
    name = tool.get("name", "")
    if not NAME_RX.fullmatch(name or ""):
        out.append(f"name {name!r} is not 1-64 of A-Z a-z 0-9 _ . -")
    title = tool.get("title")
    if not isinstance(title, str) or not title.strip():
        out.append("no top-level title")
    notes = tool.get("annotations")
    if not isinstance(notes, dict):
        out.append("no annotations object")
    else:
        if notes.get("title") != title:
            out.append("annotations.title differs from the top-level title")
        for hint in HINTS:
            if type(notes.get(hint)) is not bool:
                out.append(f"{hint} is not set explicitly")
        if notes.get("readOnlyHint") is True and notes.get("destructiveHint") is True:
            out.append("readOnlyHint and destructiveHint are both true")
    desc = tool.get("description", "")
    if not isinstance(desc, str) or len(desc.split()) < 4:
        out.append("description is missing or too short to say what it does")
        return out
    low = desc.lower()
    out += [f"description overclaims ({p})" for p in OVERCLAIMS if re.search(p, low)]
    out += [f"description coerces a call ({p})" for p in COERCIONS
            if re.search(p, low)]
    if VERIFY_WORDS.search(desc) and not BOUNDS.search(desc):
        out.append("description claims verification with no stated limit")
    props = (tool.get("inputSchema") or {}).get("properties") or {}
    out += [f"input property {key!r} breaks the name rule"
            for key in props if not NAME_RX.fullmatch(key)]
    return out


def _server_modules() -> list[str]:
    found = []
    for path in HARNESS.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r'method\s*==\s*"tools/list"', text):
            rel = path.relative_to(ROOT).with_suffix("")
            found.append(".".join(rel.parts))
    return sorted(found)


def _tools(module_name: str) -> list[dict]:
    module = importlib.import_module(module_name)
    handler = getattr(module, "handle_request", None) or module.handle
    return handler({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]


SERVERS = _server_modules()
ALL_TOOLS = [(m, t) for m in SERVERS for t in _tools(m)]


def test_discovery_finds_every_known_server():
    # A discovery that found nothing would let every test below pass vacuously.
    assert KNOWN_SERVERS <= set(SERVERS)
    assert len(ALL_TOOLS) >= 26


@pytest.mark.parametrize("module_name,tool", ALL_TOOLS,
                         ids=[f"{m}:{t['name']}" for m, t in ALL_TOOLS])
def test_every_served_tool_is_titled_hinted_and_bounded(module_name, tool):
    assert problems(tool) == []


def test_hints_agree_with_the_lane_effect_for_that_tool():
    tools = {t["name"]: t for m, t in ALL_TOOLS
             if m in ("harness.local_mcp", "harness.writing_mcp")}
    lanes = {**agents_policy.AGENT_LANE_POLICY["local-model"],
             **agents_policy.AGENT_LANE_POLICY["writing"]}
    checked = 0
    for name, entry in lanes.items():
        notes = tools[name]["annotations"]
        if entry["effect"] in WRITE_EFFECTS:
            assert notes["readOnlyHint"] is False, name
        if entry["effect"] in OPEN_EFFECTS:
            assert notes["openWorldHint"] is True, name
        checked += 1
    assert checked == len(tools)


def _files_under(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*")}


def test_a_tool_that_creates_state_on_first_call_is_not_read_only(tmp_path):
    """writing.status and writing.doctor create the owner ref on first call.

    The control half: the detector used by the next test sees those writes, so
    a read-only tool that wrote would not slip past it.
    """
    from harness import writing_mcp
    for name in ("writing.status", "writing.doctor"):
        home = tmp_path / name
        writing_mcp.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                    "params": {"name": name,
                                               "arguments": {"home": str(home)}}})
        assert _files_under(home), name
        tool = next(t for t in writing_mcp.TOOLS if t["name"] == name)
        assert tool["annotations"]["readOnlyHint"] is False


OFFLINE_CALLS = {
    "harness.writing_lint.mcp": {"writing.profiles": {},
                                 "writing.lint": {"text": "A short draft."},
                                 "writing.delta": {"old_text": "a b", "new_text": "a b c"}},
    "harness.local_mcp": {"local-model.status": {}, "local-model.doctor": {}},
}


def test_read_only_tools_write_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    ran = 0
    for module_name, calls in OFFLINE_CALLS.items():
        module = importlib.import_module(module_name)
        handler = getattr(module, "handle_request", None) or module.handle
        for name, args in calls.items():
            tool = next(t for m, t in ALL_TOOLS if m == module_name and t["name"] == name)
            assert tool["annotations"]["readOnlyHint"] is True, name
            before = _files_under(tmp_path)
            handler({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                     "params": {"name": name, "arguments": args}})
            assert _files_under(tmp_path) == before, name
            ran += 1
    assert ran == sum(len(c) for c in OFFLINE_CALLS.values())


# False-success controls: the checker itself has to catch each defect.
GOOD = {"name": "demo.tool", "title": "Demo tool",
        "description": "Return the demo value for a key the caller names.",
        "annotations": {"title": "Demo tool", "readOnlyHint": True,
                        "destructiveHint": False, "idempotentHint": True,
                        "openWorldHint": False},
        "inputSchema": {"type": "object", "properties": {"key": {"type": "string"}}}}


def _variant(**changes) -> dict:
    tool = {**GOOD, "annotations": dict(GOOD["annotations"])}
    for key, value in changes.items():
        if key in HINTS or key == "atitle":
            tool["annotations"][key if key != "atitle" else "title"] = value
        else:
            tool[key] = value
    return tool


def test_the_checker_passes_a_well_formed_tool():
    assert problems(GOOD) == []


@pytest.mark.parametrize("tool,expected", [
    ({k: v for k, v in GOOD.items() if k != "title"}, "no top-level title"),
    ({k: v for k, v in GOOD.items() if k != "annotations"}, "no annotations object"),
    (_variant(readOnlyHint=None), "readOnlyHint is not set"),
    (_variant(destructiveHint=None), "destructiveHint is not set"),
    (_variant(idempotentHint="yes"), "idempotentHint is not set"),
    (_variant(readOnlyHint=True, destructiveHint=True), "both true"),
    (_variant(atitle="Other"), "annotations.title differs"),
    (_variant(name="x" * 65), "is not 1-64"),
    (_variant(description="Guarantees the value is right for any key."), "overclaims"),
    (_variant(description="Proves that the answer is correct."), "overclaims"),
    (_variant(description="Search the store before assuming context is new."),
     "coerces a call"),
    (_variant(description="Verify the bundle and report what matched."),
     "no stated limit"),
    (_variant(inputSchema={"type": "object", "properties": {"bad key": {}}}),
     "breaks the name rule"),
])
def test_the_checker_catches_each_defect(tool, expected):
    assert any(expected in p for p in problems(tool)), problems(tool)


def test_a_bounded_verification_claim_passes():
    tool = _variant(description="Verify the bundle hashes. A match does not show "
                                "the receipts are true.")
    assert problems(tool) == []

