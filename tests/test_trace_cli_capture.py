"""The capture settings CLI and the captured-turn adapters."""
import os

from harness import trace_cli, trace_witness
from harness.capture_hooks.protocol import commitment
from trace_enc_fakes import StreamTestProvider, using
from turn_fixtures import OWNER, SESSION


def test_show_then_switch_content_on_with_presence(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    monkeypatch.setattr(trace_witness, "default_sink", trace_witness.MemorySink)
    assert trace_cli.main(["capture", "show"]) == 0
    assert "Content capture off" in capsys.readouterr().out
    monkeypatch.setattr("builtins.input", lambda *a: "yes")
    assert trace_cli.main(["capture", "content", "on"]) == 0
    out = capsys.readouterr().out
    assert "second copy" in out and "Adopted (presence: none" in out
    trace_cli.main(["capture", "show"])
    assert "Content capture on" in capsys.readouterr().out


def test_a_typed_no_leaves_the_change_pending(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    monkeypatch.setattr("builtins.input", lambda *a: "no")
    assert trace_cli.main(["capture", "content", "on"]) == 1
    assert "Not adopted (PRESENCE_DENIED)" in capsys.readouterr().out
    trace_cli.main(["capture", "show"])
    out = capsys.readouterr().out
    assert "Content capture off" in out and "not in effect" in out


def test_the_turn_adapters_export_and_delete_with_keys(tmp_path):
    from harness.trace_keystore import Keystore
    from harness.trace_turn_store import TurnStore, delete_all, export_records
    (tmp_path / "state").mkdir()
    with using(StreamTestProvider()):
        store = TurnStore(tmp_path, OWNER)
        salt = os.urandom(32)
        store.prompt("claude-code", SESSION, "pid-1",
                     commitment=commitment("prompt", salt, "p"), salt=salt)
        result = store.stop("claude-code", SESSION, "pid-1",
                            commitment=commitment("answer", salt, "a"), salt=salt)
        exported = export_records(tmp_path)
        assert [t["turn_ref"] for t in exported] == [result["turn_ref"]]
        assert delete_all(tmp_path)["removed"] >= 2
        assert not Keystore(tmp_path / "state", OWNER).present("CT", result["turn_ref"])
    assert not list((tmp_path / "state" / "captured-turns").rglob("*.enc"))


def test_the_copy_says_plaintext_when_there_is_no_os_key_store(tmp_path, monkeypatch, capsys):
    """D5: with no key store content is kept in plaintext; no string says encrypted."""
    from harness.trace_enc import NoProvider
    from trace_enc_fakes import using
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    monkeypatch.setattr(trace_witness, "default_sink", trace_witness.MemorySink)
    monkeypatch.setattr("builtins.input", lambda *a: "yes")
    with using(NoProvider()):
        assert trace_cli.main(["capture", "content", "on"]) == 0
    out = capsys.readouterr().out
    assert "kept in plaintext (no OS key store" in out
    assert "encrypted" not in out.replace("kept encrypted", "!")
    assert "kept encrypted" not in out
