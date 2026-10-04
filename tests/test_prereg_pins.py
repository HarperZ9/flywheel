"""One-command checks for preregistration pins and the prereg ledger.

``harness.prereg_pins`` reads the file pins out of a preregistration and checks
them; ``harness.prereg_verify`` checks the ledger and its signed heads. Both
must say MATCH on this repository and must flip on a one-byte change. The
EOL case is the one that used to read as a bare DRIFT on Windows.
"""
import hashlib
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness import prereg_pins, prereg_verify  # noqa: E402

DOC = "project-docs/prereg/2026-10-04-shapley-placebo.md"


def test_pins_are_found_in_the_shapley_preregistration():
    text = (ROOT / DOC).read_text(encoding="utf-8")
    pins = dict(prereg_pins.find_pins(text, ROOT))
    assert set(pins) == {"project-docs/records/2026-10-04-shapley-placebo/items-v1.json",
                         "harness/shapley_far.py", "scripts/shapley_placebo_run.py"}


def _mini(tmp_path: Path, body: bytes) -> Path:
    (tmp_path / "src").mkdir(parents=True)
    (tmp_path / "src" / "mod.py").write_bytes(body)
    digest = hashlib.sha256(b"x = 1\ny = 2\n").hexdigest()
    doc = tmp_path / "prereg.md"
    doc.write_text(f"| Module | `src/mod.py`, sha256 `{digest}` |\n", encoding="utf-8")
    return doc


def test_match_drift_and_eol_only_exit_codes(tmp_path, capsys):
    doc = _mini(tmp_path / "a", b"x = 1\ny = 2\n")
    assert prereg_pins.main([str(doc), "--root", str(tmp_path / "a")]) == 0
    doc = _mini(tmp_path / "b", b"x = 1\r\ny = 2\r\n")
    assert prereg_pins.main([str(doc), "--root", str(tmp_path / "b")]) == 3
    assert "line endings differ" in capsys.readouterr().out
    doc = _mini(tmp_path / "c", b"x = 1\ny = 3\n")
    assert prereg_pins.main([str(doc), "--root", str(tmp_path / "c")]) == 1


def test_a_document_with_no_pins_is_unverifiable(tmp_path):
    doc = tmp_path / "empty.md"
    doc.write_text("no pins here\n", encoding="utf-8")
    assert prereg_pins.main([str(doc), "--root", str(tmp_path)]) == 2


def test_prereg_ledger_verifies_and_says_where_the_key_came_from(capsys):
    assert prereg_verify.main(["--dir", str(ROOT / "artifacts" / "prereg")]) == 0
    out = capsys.readouterr().out
    assert "verdict: MATCH" in out and "key source: self" in out


def test_prereg_ledger_change_is_drift(tmp_path, capsys):
    copy = tmp_path / "prereg"
    shutil.copytree(ROOT / "artifacts" / "prereg", copy)
    ledger = copy / "ledger.jsonl"
    text = ledger.read_text(encoding="utf-8")
    ledger.write_text(text.replace('"addendum_id": "', '"addendum_id": "x', 1), encoding="utf-8")
    assert prereg_verify.main(["--dir", str(copy)]) == 1
    assert "body does not match its digest" in capsys.readouterr().out
