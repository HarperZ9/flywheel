"""Names from transcripts and paths reach the terminal escaped (SP-31).

A project directory, a `cwd` value or a file name is attacker-shaped text: an
ESC sequence in it can recolor, move the cursor, retitle the window or hide a
line. Every trace CLI prints such names through one helper.
"""
from itertools import product
import os
import re

import pytest

from harness import trace_cli, trace_cli_text

_ESCAPE = re.compile(r"\\\\|\\x([0-9a-f]{2})|\\u([0-9a-f]{4})")


def _decode(shown: str) -> str:
    """The reader's side: turn printed text back into the name it shows."""
    def one(match):
        if match.group(0) == "\\\\":
            return "\\"
        return chr(int(match.group(1) or match.group(2), 16))
    return _ESCAPE.sub(one, shown)


def test_esc_sequence_in_a_planted_project_name_is_printed_escaped():
    name = "proj\x1b[31mred\x1b]0;owned\x07"
    shown = trace_cli_text.escape(name)
    assert "\x1b" not in shown and "\x07" not in shown
    assert shown == "proj\\x1b[31mred\\x1b]0;owned\\x07"


@pytest.mark.parametrize("raw, shown", [
    ("tab\there", "tab\\x09here"),
    ("new\nline", "new\\x0aline"),
    ("cr\rreturn", "cr\\x0dreturn"),
    ("del\x7fchar", "del\\x7fchar"),
    ("c1\x9bcsi", "c1\\x9bcsi"),
    ("bidi\u202eevil", "bidi\\u202eevil"),
    ("isolate\u2066x\u2069", "isolate\\u2066x\\u2069"),
    ("back\\slash", "back\\slash"),
    ("C:\\Users\\name\\proj", "C:\\Users\\name\\proj"),
    ("literal\\x1b", "literal\\\\x1b"),
    ("double\\\\slash", "double\\\\\\slash"),
    ("slash-then-esc\\\x1b", "slash-then-esc\\\\\\x1b"),
    ("plain name-1.jsonl", "plain name-1.jsonl"),
    ("naïve café", "naïve café"),
])
def test_control_bidi_and_backslash_are_escaped_and_plain_text_is_kept(raw, shown):
    assert trace_cli_text.escape(raw) == shown
    assert _decode(shown) == raw


@pytest.mark.parametrize("alphabet, size", [
    (["\\", "x", "1", "b", "\x1b", "\n", "a"], 5),
    (["\\", "u", "2", "0", "e", "\u202e"], 6),
])
def test_escaping_is_injective_so_two_names_never_print_the_same(alphabet, size):
    """Decoding every printed form gives back its name, so a planted name can
    never pose as another one, and nothing unescaped reaches the terminal."""
    for length in range(size + 1):
        for chars in product(alphabet, repeat=length):
            raw = "".join(chars)
            shown = trace_cli_text.escape(raw)
            assert not any(ord(c) < 0x20 or c == "\u202e" for c in shown)
            assert _decode(shown) == raw, (raw, shown)


@pytest.mark.skipif(os.name == "nt", reason="NTFS refuses control characters in names")
def test_status_prints_an_unregistered_name_with_its_escape_shown(
        tmp_path, monkeypatch, capsys):
    home = tmp_path / "home"
    (home / "state" / "evil\x1b[2Jname").mkdir(parents=True)
    monkeypatch.setenv("FLYWHEEL_HOME", str(home))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "no-claude"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "no-codex"))
    assert trace_cli.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "\x1b" not in out and "evil\\x1b[2Jname" in out
