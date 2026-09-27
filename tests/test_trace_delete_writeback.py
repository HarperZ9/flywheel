"""SP-15, I19: a deletion made while the gateway runs is not undone by the
gateway. After apply, every gateway write path runs again (a captured turn
in the same session, a new agent trace, a scaffold receipt, a presence
challenge) and the deleted refs stay absent. With no OS key store the
stores are plaintext, so the residual scan there is a real check (it finds
the canary before the deletion); with encryption the scan cannot see through
ciphertext, so the test asserts the refs and keys are gone instead."""
import json
import urllib.request

import pytest

from capture_channel_fixture import prompt_event, run_hook, running_gateway, stop_event
from delete_fixtures import CANARY, OWNER, plant_trace, plant_turn
from harness.trace_residual_scan import Needles, scan_paths
from trace_enc_fakes import StreamTestProvider, using


def _bearer_post(port, token, path, body):
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                     data=json.dumps(body).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {token}",
                                              "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read())


def _files(home):
    return [p for p in home.rglob("*") if p.is_file()]


def _absent(home, trace_ref, turn_ref) -> None:
    from delete_fixtures import JOURNEY, OPERATION
    from harness.gateway_agent_trace import AgentTrace
    from harness.trace_keystore import Keystore
    from harness.trace_turn_store import TurnStore
    assert AgentTrace(home / "state", OWNER, JOURNEY, OPERATION).read() == []
    with pytest.raises(FileNotFoundError):
        TurnStore(home, OWNER).read_turn(turn_ref)
    keystore = Keystore(home / "state", OWNER)
    assert not keystore.present("S1", trace_ref) and not keystore.present("CT", turn_ref)


@pytest.mark.parametrize("provider", ["stream", "none"])
def test_the_gateway_does_not_write_deleted_content_back(tmp_path, monkeypatch, provider):
    from harness.trace_enc import NoProvider
    home, work = tmp_path / "home", tmp_path / "work"
    home.mkdir()
    work.mkdir()
    (home / "owner.ref").write_text(OWNER)
    chosen = StreamTestProvider() if provider == "stream" else NoProvider()
    with using(chosen), running_gateway(home, monkeypatch) as server:
        port, token = server.server_address[1], (home / "gateway.token").read_text().strip()
        trace_ref, turn = plant_trace(home), plant_turn(home)
        if provider == "none":  # control: the scan sees plaintext before the deletion
            assert scan_paths(_files(home), Needles.build([CANARY]))["total"] > 0
        plan = _bearer_post(port, token, "/api/traces/delete/plan",
                            {"trace_refs": [trace_ref], "turn_refs": [turn["turn_ref"]]})
        presence = _bearer_post(port, token, "/api/traces/presence",
                                {"kind": "delete_apply", "plan_digest": plan["plan_digest"]})
        report = _bearer_post(port, token, "/api/traces/delete/apply",
                              {"plan_digest": plan["plan_digest"], "presence_ref": presence["ref"]})
        assert report["state"] == "DELETED"
        run_hook(home, "prompt", prompt_event("a new prompt", prompt_id="pid-7"), cwd=work)
        run_hook(home, "stop", stop_event("a new answer", prompt_id="pid-7"), cwd=work)
        plant_trace(home, operation="op_" + "e" * 32, text="unrelated result")
        _bearer_post(port, token, "/api/scaffold", {"prompt": "no links", "answer": "done"})
        _absent(home, trace_ref, turn["turn_ref"])
    assert scan_paths(_files(home), Needles.build([CANARY]))["total"] == 0
