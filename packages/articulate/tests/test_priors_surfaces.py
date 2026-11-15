"""Printed surfaces agree with their own counts, and limit lines read as scope."""
import json
import pathlib
import re

from articulate import cli

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_the_printed_summary_agrees_with_the_json_findings(tmp_path, capsys):
    # PU30-50: a summary and its log come from one count.
    doc = tmp_path / "n.md"
    doc.write_text("I hope this finds you well. The release is ready \u2014 ship it. "
                   "Let me know if you have any questions.\n", encoding="utf-8")
    cli.main(["check", str(doc), "--profile", "note"])
    printed = capsys.readouterr().out
    cli.main(["check", str(doc), "--profile", "note", "--json"])
    result = json.loads(capsys.readouterr().out)["results"][0]
    head = re.search(r"(\d+) high, (\d+) medium", printed)
    assert head and (int(head.group(1)), int(head.group(2))) == (len(result["high"]),
                                                                  len(result["medium"]))
    rows = [ln for ln in printed.splitlines() if re.match(r"\s+L\d+ \[(HIGH|MEDIUM)", ln)]
    assert len(rows) == len(result["high"]) + len(result["medium"])
    gating = len(result["high"]) + sum(1 for f in result["medium"]
                                       if f["category"] in ("note-opener", "note-closing-offer"))
    assert result["blocking_count"] == gating


def test_edit_limit_lines_read_as_scope():
    # R20: state the limit beside the claim in plain words, with no does-not-prove line.
    surfaces = [ROOT / "claude-plugin" / "skills" / "prose-edit" / "SKILL.md",
                ROOT / "claude-plugin" / "README.md",
                ROOT / "src" / "articulate" / "hosted_mcp.py"]
    for path in surfaces:
        text = path.read_text(encoding="utf-8")
        assert "not prove semantic equivalence" not in text, path
    skill = surfaces[0].read_text(encoding="utf-8")
    assert "check words and protected spans only" in skill
