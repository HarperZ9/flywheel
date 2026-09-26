"""The import CLI plans by default, imports with --apply, and prints names
from the client's folder with control characters escaped."""
from harness import trace_cli
from import_fixtures import OWNER, claude_tree
from trace_enc_fakes import StreamTestProvider, using


def _setup(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "state").mkdir(parents=True)
    (home / "owner.ref").write_text(OWNER)
    root, _, _ = claude_tree(tmp_path)
    monkeypatch.setenv("FLYWHEEL_HOME", str(home))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(root))
    return home, root


def test_the_default_run_plans_and_imports_nothing(tmp_path, monkeypatch, capsys):
    home, _ = _setup(tmp_path, monkeypatch)
    with using(StreamTestProvider()):
        assert trace_cli.main(["import", "claude-code"]) == 0
    out = capsys.readouterr().out
    assert "new: 5 files" in out and "sweep risk: 0 transcripts" in out
    assert "not imported history.jsonl: NOT_IMPORTED_BY_DEFAULT (--with-prompt-history)" in out
    assert "Nothing was imported" in out
    assert not (home / "state" / "imports").exists()


def test_apply_imports_and_reports(tmp_path, monkeypatch, capsys):
    _setup(tmp_path, monkeypatch)
    with using(StreamTestProvider()):
        assert trace_cli.main(["import", "claude-code", "--apply"]) == 0
    assert "Imported 5 files" in capsys.readouterr().out


def test_a_hostile_project_name_is_printed_escaped(tmp_path, monkeypatch, capsys):
    _, root = _setup(tmp_path, monkeypatch)
    hostile = root / "projects" / "evil\x1b[2Jname"
    try:
        hostile.mkdir()
    except OSError:
        import pytest
        pytest.skip("the file system refuses control characters in names")
    (hostile / "x.jsonl").write_bytes(b"{}\n")
    with using(StreamTestProvider()):
        trace_cli.main(["import", "claude-code"])
    assert "\x1b" not in capsys.readouterr().out
