"""The presence method at the CLI: status and show name it and what `none`
means; a change needs the method already in effect to confirm it."""
from harness import trace_cli
from harness import trace_presence_verifiers as verifiers


def test_status_and_show_name_the_method_and_what_none_means(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    assert trace_cli.main(["status"]) == 0
    assert "Presence: none: any process running as the owner, agents included" in (
        capsys.readouterr().out)
    assert trace_cli.main(["presence", "show"]) == 0
    assert "Presence method: none" in capsys.readouterr().out


def test_set_is_confirmed_by_the_current_method(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    monkeypatch.setattr("builtins.input", lambda *a: "yes")
    assert trace_cli.main(["presence", "set", "windows-hello"]) == 0
    assert "Presence method is now windows-hello (confirmed by none" in capsys.readouterr().out
    monkeypatch.setattr(verifiers.WindowsHelloVerifier, "ask", lambda self, summary: False)
    assert trace_cli.main(["presence", "set", "none"]) == 1
    assert "Not changed (PRESENCE_DENIED)" in capsys.readouterr().out
    assert trace_cli.main(["presence", "show"]) == 0
    assert "Presence method: windows-hello" in capsys.readouterr().out


def test_a_typed_no_changes_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    monkeypatch.setattr("builtins.input", lambda *a: "no")
    assert trace_cli.main(["presence", "set", "desktop-dialog"]) == 1
    capsys.readouterr()
    trace_cli.main(["presence", "show"])
    assert "Presence method: none" in capsys.readouterr().out
