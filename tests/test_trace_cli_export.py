"""Acceptance for 7.5: `flywheel traces export --out <dir>` then
`python <dir>/verify.py <dir>` prints MATCH, and the ledger and the witness
show the export. A typed no writes nothing; a zip export verifies too."""
import subprocess
import sys

import pytest

from delete_fixtures import OWNER
from export_fixtures import planted
from harness import trace_cli, trace_witness
from harness.trace_custody_ledger import CustodyLedger


@pytest.fixture
def world(tmp_path, monkeypatch):
    with planted(tmp_path, monkeypatch) as (home, refs):
        yield home, tmp_path


def test_export_then_its_own_verifier_prints_match(world, monkeypatch, capsys):
    home, base = world
    sink = trace_witness.MemorySink()
    monkeypatch.setattr(trace_witness, "default_sink", lambda: sink)
    monkeypatch.setattr("builtins.input", lambda *a: "yes")
    out = base / "exported"
    assert trace_cli.main(["export", "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "S1: 1 items" in printed and "redaction: credentials" in printed
    done = subprocess.run([sys.executable, str(out / "verify.py"), str(out)],
                          capture_output=True, text=True)
    assert done.returncode == 0 and done.stdout.splitlines()[0] == "MATCH"
    assert CustodyLedger(home, OWNER).entries()[-1]["kind"] == "export"
    assert [e["kind"] for e in sink.read()] == ["export"]
    assert trace_cli.main(["verify-export", str(out)]) == 0


def test_a_typed_no_writes_nothing(world, monkeypatch, capsys):
    _, base = world
    monkeypatch.setattr("builtins.input", lambda *a: "no")
    assert trace_cli.main(["export", "--out", str(base / "x")]) == 1
    assert "Nothing was written" in capsys.readouterr().out
    assert not (base / "x").exists() and not (base / "x.incomplete").exists()


def test_a_zip_export_verifies(world, monkeypatch):
    _, base = world
    monkeypatch.setattr("builtins.input", lambda *a: "yes")
    assert trace_cli.main(["export", "--out", str(base / "z"), "--zip", "--yes"]) == 0
    assert (base / "z.zip").is_file() and not (base / "z").exists()
    assert trace_cli.main(["verify-export", str(base / "z.zip")]) == 0


def test_a_grant_says_what_confirms_it_under_the_method_in_effect(world, capsys):
    """No app asks for an export grant; with the default method `none` the
    line says nothing is asked and any process with the token can run it."""
    _, base = world
    assert trace_cli.main(["export", "--out", str(base / "granted"), "--grant"]) == 0
    printed = capsys.readouterr().out
    assert "when the app asks" not in printed
    assert "presence method none" in printed and "nothing is asked" in printed
