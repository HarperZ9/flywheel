from harness.file_backed_store import FileBackedHarnessStore, read_jsonl
from scripts.run_endpoint_auth_status import _status_verdict, _store_status_outputs
from scripts.run_pubscan_resource_profiles import _store_profile_outputs


def test_pubscan_profile_outputs_store_receipt_and_artifact(tmp_path):
    artifact = tmp_path / "profile.json"
    artifact.write_text('{"schema":"harness.pubscan-resource-profiles/v1"}', encoding="utf-8")
    store_root = tmp_path / "store"

    outputs = _store_profile_outputs(
        {
            "schema": "harness.pubscan-resource-profiles/v1",
            "receipt": {"verdict": "PROFILED"},
        },
        store_root=str(store_root),
        run_id="run_pubscan",
        artifact_paths=[(str(artifact), "profile-json")],
    )

    store = FileBackedHarnessStore(store_root)
    receipts = read_jsonl(store.receipts_path)
    assert outputs[0]["schema"] == "harness.receipt/v1"
    assert outputs[0]["kind"] == "pubscan_resource_profiles"
    assert outputs[0]["verdict"] == "PROFILED"
    assert outputs[1]["schema"] == "harness.artifact/v1"
    assert len(receipts) == 1


def test_endpoint_auth_status_verdicts_are_readiness_specific():
    assert _status_verdict({"summary": {"all_configured": True}}) == "AUTH_READY"
    assert _status_verdict({"summary": {"all_configured": False}}) == "AUTH_PARTIAL"
    assert _status_verdict({}) == "AUTH_PARTIAL"


def test_endpoint_status_outputs_store_receipt_and_artifact(tmp_path):
    artifact = tmp_path / "auth.json"
    artifact.write_text('{"schema":"harness.endpoint-auth-status/v1"}', encoding="utf-8")
    store_root = tmp_path / "store"

    outputs = _store_status_outputs(
        {
            "schema": "harness.endpoint-auth-status/v1",
            "summary": {"all_configured": False},
        },
        store_root=str(store_root),
        run_id="run_auth",
        artifact_paths=[(str(artifact), "auth-json")],
    )

    store = FileBackedHarnessStore(store_root)
    receipts = read_jsonl(store.receipts_path)
    assert outputs[0]["schema"] == "harness.receipt/v1"
    assert outputs[0]["kind"] == "endpoint_auth_status"
    assert outputs[0]["verdict"] == "AUTH_PARTIAL"
    assert outputs[1]["schema"] == "harness.artifact/v1"
    assert len(receipts) == 1
