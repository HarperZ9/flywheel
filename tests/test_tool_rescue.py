"""The witnessed rescue loop (landscape import 6, the Forge pattern done
honestly): malformed tool emissions are repaired by named deterministic
transforms, and every repair is a visible record — original, transform,
repaired — never a silent in-proxy fix. Clean emissions are untouched and
unrescuable garbage stays garbage."""

from harness.tool_rescue import rescue_tool_calls

CLEAN = 'TOOL read_file {"path": "a.py"}'
FENCED = '`TOOL read_file {"path": "a.py"}`'
SINGLES = "TOOL read_file {'path': 'a.py'}"
COLON = 'TOOL: read_file {"path": "a.py"}'
GARBAGE = "I would maybe read some files now."


def test_clean_calls_pass_through_with_no_repairs():
    calls, repairs = rescue_tool_calls(CLEAN)
    assert calls == [("read_file", {"path": "a.py"})]
    assert repairs == []


def test_backticked_call_is_rescued_and_witnessed():
    calls, repairs = rescue_tool_calls(FENCED)
    assert calls == [("read_file", {"path": "a.py"})]
    assert len(repairs) == 1
    assert repairs[0]["transform"] == "strip_inline_backticks"
    assert "TOOL read_file" in repairs[0]["original"]


def test_single_quotes_are_rescued_and_witnessed():
    calls, repairs = rescue_tool_calls(SINGLES)
    assert calls == [("read_file", {"path": "a.py"})]
    assert repairs[0]["transform"] == "single_to_double_quotes"


def test_colon_variant_is_rescued_and_witnessed():
    calls, repairs = rescue_tool_calls(COLON)
    assert calls == [("read_file", {"path": "a.py"})]
    assert repairs[0]["transform"] == "strip_tool_colon"


def test_garbage_stays_garbage():
    calls, repairs = rescue_tool_calls(GARBAGE)
    assert calls == []
    assert repairs == []
