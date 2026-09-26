"""D5 and I7: with no OS key store, status says plaintext in plain words, and
with one it names the provider and the floor per store."""
from harness import trace_cli, trace_inventory_scan
from harness.gateway_agent_trace import AgentTrace
from harness.trace_enc import NoProvider
from trace_enc_fakes import StreamTestProvider, using

OWNER = "owner_" + "a" * 32


def _scan(home, run_root):
    return trace_inventory_scan.scan(environ={"FLYWHEEL_HOME": str(home),
                                              "FLYWHEEL_RUN_ROOT": str(run_root)})


def _status(home, run_root) -> str:
    doc = _scan(home, run_root)
    return "\n".join(trace_cli.render_status(doc, {"home": str(home), "run": str(run_root)}))


def test_no_provider_is_reported_as_plaintext_with_no_os_key_store(tmp_path):
    home, run_root = tmp_path / "home", tmp_path / "run"
    home.mkdir(); run_root.mkdir()
    with using(NoProvider()):
        doc = _scan(home, run_root)
        text = _status(home, run_root)
    assert doc["encryption"]["provider"] == "none"
    assert doc["encryption"]["protection"] == "plaintext (no OS key store)"
    assert "plaintext (no OS key store)" in text


def test_a_provider_is_named_and_the_floor_shows_after_the_first_encrypted_write(tmp_path):
    home, run_root = tmp_path / "home", tmp_path / "run"
    (home / "state").mkdir(parents=True); run_root.mkdir()
    with using(StreamTestProvider()):
        assert _scan(home, run_root)["encryption"]["floors"] == {}
        AgentTrace(home / "state", OWNER, "jrn_" + "b" * 32, "op_" + "c" * 32).append(
            "progress", {"index": 0})
        doc = _scan(home, run_root)
        text = _status(home, run_root)
    assert doc["encryption"]["protection"] == "encrypted (test)"
    assert doc["encryption"]["floors"] == {"S1": True}
    assert "encrypted (test)" in text and "floor" in text


def test_the_json_document_still_validates(tmp_path):
    from harness.trace_inventory import validate_document
    home, run_root = tmp_path / "home", tmp_path / "run"
    home.mkdir(); run_root.mkdir()
    with using(NoProvider()):
        assert validate_document(_scan(home, run_root)) == []
