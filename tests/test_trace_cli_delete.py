"""The deletion CLI prints the plan, applies it after a typed confirmation
under the `none` method, and verify-gone reads the phrase from standard input
and reports hits per file, never text."""
import io

from delete_fixtures import CANARY, OWNER, plant_trace
from harness import trace_cli, trace_witness
from trace_enc_fakes import StreamTestProvider, using


def _home(tmp_path, monkeypatch):
    (tmp_path / "owner.ref").write_text(OWNER)
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    monkeypatch.setenv("FLYWHEEL_RUN_ROOT", str(tmp_path / "run"))
    monkeypatch.setattr(trace_witness, "default_sink", trace_witness.MemorySink)
    return tmp_path


def test_plan_then_apply(tmp_path, monkeypatch, capsys):
    home = _home(tmp_path, monkeypatch)
    with using(StreamTestProvider()):
        ref = plant_trace(home)
        assert trace_cli.main(["delete", "--trace-ref", ref]) == 0
        out = capsys.readouterr().out
        assert "S1: 1 items, keys destroyed first" in out and "outside reach: provider" in out
        digest = out.split("Plan digest ")[1].split()[0]
        monkeypatch.setattr("builtins.input", lambda *a: "yes")
        assert trace_cli.main(["delete", "--apply", "--plan-digest", digest]) == 0
    assert "DELETED" in capsys.readouterr().out


def test_verify_gone_reads_stdin_and_never_prints_the_phrase(tmp_path, monkeypatch, capsys):
    home = _home(tmp_path, monkeypatch)
    (home / "state").mkdir()
    (home / "state" / "left-behind.txt").write_text(CANARY)
    monkeypatch.setattr("sys.stdin", io.StringIO(CANARY))
    assert trace_cli.main(["verify-gone"]) == 1
    out = capsys.readouterr().out
    assert "left-behind.txt" in out and "hits" in out and CANARY[:40] not in out
