"""The advisory edit-time hook: event parsing, findings, locality and launch.

Claude Code sends Write, Edit and MultiEdit tool input with the file path and the
text. Codex sends apply_patch with the patch body in tool_input.command. The hook
answers with hookSpecificOutput.additionalContext for prose files and with
nothing otherwise, and it always exits 0. Each finding test has a control that
stays quiet, so a passing run is a finding about the hook and not a hook that
prints on every event.
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
from articulate import edit_hook
from claude_plugin_helpers import load

PKG = pathlib.Path(articulate.__file__).resolve().parent
CAVEAT = ("We used a cache that may reduce latency. In 12 local tests, latency fell "
          "from 20 ms to 18 ms. This does not establish a production benefit.")


def _event(tool_name, tool_input, **extra):
    return dict({"hook_event_name": "PostToolUse", "session_id": "s", "cwd": "/w",
                 "tool_name": tool_name, "tool_input": tool_input}, **extra)


def _run(event, env=None):
    out, err = io.StringIO(), io.StringIO()
    raw = event if isinstance(event, bytes) else json.dumps(event).encode("utf-8")
    old = dict(os.environ)
    os.environ.update(env or {})
    try:
        code = edit_hook.main(io.BytesIO(raw), out, err)
    finally:
        os.environ.clear()
        os.environ.update(old)
    return code, out.getvalue(), err.getvalue()


def _context(stdout):
    answer = json.loads(stdout)
    assert answer["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    return answer["hookSpecificOutput"]["additionalContext"]


def _edit(old, new, path="/w/docs/notes.md"):
    return _event("Edit", {"file_path": path, "old_string": old, "new_string": new})


def test_an_edit_that_drops_a_modal_and_changes_a_number_is_named():
    code, out, _ = _run(_edit(CAVEAT, CAVEAT.replace("may reduce", "reduces")
                              .replace("18 ms", "16 ms")))
    text = _context(out)
    assert code == 0
    assert "dropped modal 'may'" in text and "'18 ms'" in text and "'16 ms'" in text
    assert "notes.md" in text and "These notes are advice" in text


def test_an_edit_that_keeps_every_fact_and_reads_clean_says_nothing():
    code, out, err = _run(_edit(CAVEAT, CAVEAT.replace("We used", "We added")))
    assert (code, out, err) == (0, "", "")


@pytest.mark.parametrize("old,new,needle", [
    ("This does not establish a benefit.", "This establishes a benefit.", "negation"),
    ("It applies only to this fixture.", "It applies to this fixture.", "scope"),
    ("Details: https://example.org/a.", "Details: https://example.org/b.", "url"),
    ('She said "replicate it first."', 'She said "replicate it."', "quote"),
    ("See [4] for methods.", "See [5] for methods.", "citation"),
])
def test_each_preserved_kind_is_reported_when_an_edit_changes_it(old, new, needle):
    assert needle in _context(_run(_edit(old, new))[1])


def test_a_write_reports_style_findings_in_the_new_text():
    event = _event("Write", {"file_path": "/w/README.md", "content":
                             "This is not just a tool, it is a game-changer. We delve in.\n"})
    text = _context(_run(event)[1])
    assert "style findings" in text and "delve" in text
    assert "possible meaning change" not in text  # a write has no before text


def test_multiedit_checks_every_edit():
    event = _event("MultiEdit", {"file_path": "/w/a.md", "edits": [
        {"old_string": "It may work.", "new_string": "It works."},
        {"old_string": "We did not test it.", "new_string": "We tested it."}]})
    text = _context(_run(event)[1])
    assert "modal" in text and "negation" in text


@pytest.mark.parametrize("path", ["/w/app.py", "/w/data.json", "/w/Makefile", None])
def test_files_that_are_not_prose_are_skipped(path):
    event = _edit("It may work.", "It works.", path=path)
    assert _run(event) == (0, "", "")


PATCH = """*** Begin Patch
*** Update File: docs/guide.md
@@ intro
 Upgrade with care.
-Version 2.3 might break old plugins.
+Version 2.3 will break old plugins.
*** Add File: docs/new.md
+This is not just a guide, it is a game-changer.
*** Delete File: docs/old.md
*** Update File: src/main.py
-x = 1
+x = 2
*** End Patch"""


def test_codex_apply_patch_updates_and_adds_are_checked():
    text = _context(_run(_event("apply_patch", {"command": PATCH}))[1])
    assert "guide.md" in text and "modal" in text
    assert "new.md" in text and "style findings" in text
    assert "main.py" not in text and "old.md" not in text


def test_parse_patch_follows_moves_and_keeps_context_on_both_sides():
    patch = ("*** Begin Patch\n*** Update File: a.md\n*** Move to: b.md\n@@\n keep\n-old\n+new\n"
             "*** End Patch")
    assert edit_hook.parse_patch(patch) == [("b.md", "keep\nold", "keep\nnew")]


def test_apply_patch_given_as_an_argument_list_is_read():
    text = _context(_run(_event("apply_patch", {"command": ["apply_patch", PATCH]}))[1])
    assert "guide.md" in text


@pytest.mark.parametrize("raw", [b"not json", b"[]", b"{}", json.dumps(
    {"hook_event_name": "PreToolUse", "tool_name": "Edit", "tool_input": {
        "file_path": "a.md", "old_string": "It may.", "new_string": "It does."}}).encode()])
def test_an_event_the_hook_cannot_use_never_blocks(raw):
    code, out, _ = _run(raw)
    assert code == 0 and out == ""


def test_a_malformed_event_is_reported_on_stderr_not_swallowed():
    code, out, err = _run(b"\xff\xfe not utf-8")
    assert (code, out) == (0, "") and "skipped this event" in err


def test_an_oversized_event_is_refused_without_blocking():
    code, out, err = _run(b" " * (edit_hook.MAX_EVENT_BYTES + 10))
    assert (code, out) == (0, "") and "byte limit" in err


def test_the_switch_turns_the_hook_off():
    event = _edit("It may work.", "It works.")
    assert _run(event, {"ARTICULATE_EDIT_HOOK": "off"}) == (0, "", "")
    assert _run(event, {"ARTICULATE_EDIT_HOOK": "on"})[1]


def test_the_answer_is_ascii_json_whatever_the_text():
    out = _run(_edit("It may cost 5 €.", "It costs 6 €.", path="/w/café.md"))[1]
    assert out.isascii() and "café.md" in _context(out)


# The pre-registered guard cases (2026-10-01) that v0.6.0 rejects must also be
# named by the hook, so the edit-time path is no weaker than edit_submit.
P1 = ("We utilized a cache that may reduce latency. In 12 local tests, latency fell from "
      "20 ms to 18 ms. This does not establish a production benefit. We did not test "
      "concurrent requests. The result applies only to this fixture. Details: "
      "https://example.org/cache-test.")


@pytest.mark.parametrize("old,new", [
    ("may reduce", "reduces"), ("does not establish", "establishes"),
    ("to 18 ms", "to 16 ms"), ("cache-test", "cache-tests"),
    ("applies only to", "applies to"), ("We did not test concurrent requests. ", ""),
])
def test_the_registered_critical_alterations_are_named(old, new):
    assert "possible meaning change" in _context(_run(_edit(P1, P1.replace(old, new)))[1])


class Escaped(AssertionError):
    pass


def test_the_hook_opens_no_file_process_or_socket(monkeypatch):
    """Reading the package's own modules is allowed; anything else fails the test."""
    real_open = builtins.open

    def guarded_open(file, mode="r", *args, **kwargs):
        path = pathlib.Path(os.fsdecode(file)).resolve()
        if PKG in path.parents and not set(mode) & set("wax+"):
            return real_open(file, mode, *args, **kwargs)
        raise Escaped("open %s" % path)

    def refuse(*args, **kwargs):
        raise Escaped("process or socket")

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(io, "open", guarded_open)
    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(subprocess, "Popen", refuse)
    monkeypatch.setattr(os, "system", refuse)
    answer = edit_hook.respond(json.dumps(_edit(P1, P1.replace("may reduce", "reduces")))
                               .encode("utf-8"))
    assert "modal" in answer
    # Control: the guards do fire, so the clean run above is a finding.
    with pytest.raises(Escaped):
        open(os.path.join(os.path.dirname(str(PKG)), "outside.txt"), "w")
    with pytest.raises(Escaped):
        socket.socket()


build = load("build_claude_plugin")


@pytest.fixture(scope="module")
def plugin(tmp_path_factory):
    out = tmp_path_factory.mktemp("built") / "articulate-writing"
    build.build(out)
    return out


def _hook_command(plugin):
    cfg = json.loads((plugin / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    (entry,) = cfg["hooks"]["PostToolUse"]
    (hook,) = entry["hooks"]
    return hook["command"]


def test_the_built_plugin_runs_the_declared_hook_with_an_isolated_python(plugin):
    command = _hook_command(plugin)
    assert command.startswith("python3 -I -S -B -X utf8 ")
    script = command.split('"')[1].replace("${CLAUDE_PLUGIN_ROOT}", str(plugin))
    event = json.dumps(_edit("It may work.", "It works.")).encode("utf-8")
    run = subprocess.run([sys.executable, "-I", "-S", "-B", "-X", "utf8", script],
                         input=event, capture_output=True, timeout=60, cwd=str(plugin))
    assert run.returncode == 0, run.stderr
    assert "modal" in _context(run.stdout.decode("utf-8"))


def test_the_built_plugin_hook_exits_zero_on_garbage(plugin):
    script = _hook_command(plugin).split('"')[1].replace("${CLAUDE_PLUGIN_ROOT}", str(plugin))
    run = subprocess.run([sys.executable, "-I", "-S", "-B", script], input=b"garbage",
                         capture_output=True, timeout=60)
    assert run.returncode == 0 and run.stdout == b""


def test_the_codex_manifest_points_at_the_same_hooks_file(plugin):
    codex = json.loads((plugin / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert codex["hooks"] == "./hooks/hooks.json"
    assert (plugin / codex["hooks"]).is_file()


def test_a_changed_long_code_block_is_clipped_and_the_answer_is_bounded():
    # A changed code block is named with its whole text. Without a limit, one
    # large edit copied every changed block into the model's context.
    block = "```\n" + "\n".join("step %d runs the build" % i for i in range(150)) + "\n```"
    old = "\n\n".join("Section %d.\n\n%s" % (i, block.replace("step", "stage %d" % i))
                      for i in range(20))
    new = old.replace("runs", "starts")
    assert 50_000 < len(old) <= edit_hook.MAX_TEXT_CHARS
    code, out, _ = _run(_edit(old, new))
    context = _context(out)
    assert code == 0
    assert "changed code" in context
    assert "more characters" in context
    assert len(context) <= (edit_hook.MAX_CONTEXT_CHARS + len(edit_hook.ADVICE_NOTE) + 100)
    assert context.endswith(edit_hook.ADVICE_NOTE)


def test_clip_keeps_short_notes_and_counts_what_it_cuts():
    assert edit_hook.clip("short") == "short"
    clipped = edit_hook.clip("x" * 300, limit=100)
    assert clipped == "x" * 100 + "... (200 more characters)"


QUOTED_WRITE = ('The author said "we showcased the build and it was a delve into craft" '
                "on the call.\n> We showcased it to delve deeper.\n")


def _write(content, path="/w/docs/notes.md"):
    return _event("Write", {"file_path": path, "content": content})


def test_words_inside_quotation_marks_and_block_quotes_are_left_out():
    code, out, _ = _run(_write(QUOTED_WRITE))
    assert code == 0
    text = _context(out)
    assert "showcased" not in text and "delve" not in text
    assert "inside quotation marks or block quotes left out" in text


def test_the_same_words_outside_quotes_are_still_named():
    # Control: the quote mask must not hide the author's own sentences.
    unquoted = QUOTED_WRITE.replace('"', "").replace("> ", "")
    text = _context(_run(_write(unquoted))[1])
    assert "showcased" in text or "delve" in text
    assert "left out" not in text


def test_a_clean_file_with_quotes_says_nothing():
    code, out, _ = _run(_write('She said "see you at noon" and left.\n'))
    assert code == 0 and out == ""


def test_quoted_words_are_checked_when_the_switch_asks_for_it():
    text = _context(_run(_write(QUOTED_WRITE), {"ARTICULATE_EDIT_HOOK_QUOTES": "check"})[1])
    assert "showcased" in text or "delve" in text
    assert "left out" not in text


@pytest.mark.parametrize("line, kept", [
    ('He said "showcased" twice.\n', "He said " + " " * 11 + " twice.\n"),
    ("“delve” here\r\n", "        here\r\n"),
    ("> > quoted words\n", "> >             \n"),
    ("it's Bob's 'word'\n", "it's Bob's 'word'\n"),
    ("a > b is not a quote\n", "a > b is not a quote\n"),
])
def test_mask_quotations_keeps_length_and_line_endings(line, kept):
    masked = edit_hook.mask_quotations(line)
    assert masked == kept and len(masked) == len(line)
