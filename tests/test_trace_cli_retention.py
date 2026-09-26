"""The retention CLI: show the default, set a rule with presence, plan it,
and apply the plan with presence; a typed no leaves the change pending."""
import os
import time

from delete_fixtures import plant_trace
from harness import trace_cli, trace_witness
from harness.operation_grants import load_or_create_owner_ref
from trace_enc_fakes import StreamTestProvider, using


def _old_trace(home, owner, operation):
    from harness.gateway_agent_trace import AgentTrace
    (home / "state").mkdir(parents=True, exist_ok=True)
    trace = AgentTrace(home / "state", owner, "jrn_" + "b" * 32, operation)
    trace.append("request", {"goal": "old"})
    stamp = time.time() - 40 * 86400
    for path in (home / "state" / "gateway-agent-traces" / "v1" / "owners" / owner /
                 operation).iterdir():
        os.utime(path, (stamp, stamp))
    return trace.ref


def test_set_plan_and_apply(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    monkeypatch.setenv("FLYWHEEL_RUN_ROOT", str(tmp_path / "run"))
    monkeypatch.setattr(trace_witness, "default_sink", trace_witness.MemorySink)
    monkeypatch.setattr("builtins.input", lambda *a: "yes")
    with using(StreamTestProvider()):
        owner = load_or_create_owner_ref(tmp_path)
        assert trace_cli.main(["retention", "show"]) == 0
        assert "keep until you delete" in capsys.readouterr().out
        _old_trace(tmp_path, owner, "op_" + "1" * 32)
        assert trace_cli.main(["retention", "set", "--store", "S1", "--max-age-days", "30",
                               "--max-share", "1.0"]) == 0
        assert "The first run only plans" in capsys.readouterr().out
        assert trace_cli.main(["retention", "plan"]) == 0
        out = capsys.readouterr().out
        digest = out.split("Plan ")[1].split(":")[0]
        assert "1 items" in out
        assert trace_cli.main(["retention", "apply", "--plan-digest", digest]) == 0
        assert "APPLIED" in capsys.readouterr().out
        assert not (tmp_path / "state" / "gateway-agent-traces" / "v1" / "owners" / owner /
                    ("op_" + "1" * 32)).exists()


def test_a_typed_no_leaves_the_policy_pending(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    monkeypatch.setattr("builtins.input", lambda *a: "no")
    assert trace_cli.main(["retention", "set", "--max-items", "5"]) == 1
    assert "Not adopted (PRESENCE_DENIED)" in capsys.readouterr().out
    trace_cli.main(["retention", "show"])
    out = capsys.readouterr().out
    assert "keep until you delete" in out and "not in effect" in out


def test_status_keeps_its_default_line(tmp_path, monkeypatch):
    with using(StreamTestProvider()):
        plant_trace(tmp_path)
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    from harness.trace_inventory_scan import scan
    assert scan()["retention"]["action"] == "keep"
