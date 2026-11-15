"""Falsifiers for the conventions-file gap-close (parity with aider's CONVENTIONS.md).

Load-bearing: (1) the first matching filename wins, in the documented order;
(2) no file present -> the system prompt is unchanged, never a spurious note;
(3) an oversized file is truncated and FLAGGED, never silently cut with no trace;
(4) `with_conventions` appends, it never replaces, the caller's system prompt.
"""
from relay.conventions import FILENAMES, load_conventions, with_conventions


def test_no_conventions_file_leaves_system_unchanged(tmp_path):
    assert load_conventions(str(tmp_path)) is None
    assert with_conventions("base prompt", str(tmp_path)) == "base prompt"


def test_first_matching_filename_wins_in_documented_order(tmp_path):
    assert FILENAMES[0] == "AGENTS.md"
    (tmp_path / "CONVENTIONS.md").write_text("use tabs", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("use spaces", encoding="utf-8")
    found = load_conventions(str(tmp_path))
    assert found["path"] == "AGENTS.md" and found["text"] == "use spaces"


def test_falls_back_to_the_next_filename_when_the_first_is_absent(tmp_path):
    (tmp_path / "CONVENTIONS.md").write_text("use tabs", encoding="utf-8")
    found = load_conventions(str(tmp_path))
    assert found["path"] == "CONVENTIONS.md" and found["truncated"] is False


def test_oversized_file_is_truncated_and_flagged_not_silently_cut(tmp_path):
    big = "x" * 50
    (tmp_path / "AGENTS.md").write_text(big, encoding="utf-8")
    found = load_conventions(str(tmp_path), max_chars=10)
    assert len(found["text"]) == 10 and found["truncated"] is True
    out = with_conventions("base", str(tmp_path), max_chars=10)
    assert "truncated" in out          # the cut is visible, not hidden


def test_with_conventions_appends_never_replaces(tmp_path):
    (tmp_path / "AGENTS.md").write_text("no em-dashes", encoding="utf-8")
    out = with_conventions("You are a coding agent.", str(tmp_path))
    assert out.startswith("You are a coding agent.")
    assert "no em-dashes" in out and "AGENTS.md" in out
