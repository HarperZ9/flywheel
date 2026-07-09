import json

from harness.file_backed_store import FileBackedHarnessStore, read_jsonl


def test_file_backed_store_records_run_events_and_receipt(tmp_path):
    store = FileBackedHarnessStore(tmp_path / "store")

    run = store.create_run(kind="pubscan_profile", title="profile pubscan")
    receipt = store.put_receipt(
        kind="profile_bundle",
        run_id=run["run_id"],
        body={"schema": "example.profile/v1", "ok": True},
        verdict="PROFILED",
    )

    assert run["schema"] == "harness.run/v1"
    assert receipt["schema"] == "harness.receipt/v1"
    assert receipt["payload_sha256"]
    assert store.runs_path.exists()
    assert store.events_path.exists()
    assert store.receipts_path.exists()
    assert len(read_jsonl(store.runs_path)) == 1
    assert len(read_jsonl(store.receipts_path)) == 1
    assert len(read_jsonl(store.events_path)) == 2

    body = json.loads((store.receipt_body_dir / f"{receipt['payload_sha256']}.json").read_text())
    assert body["body"]["ok"] is True


def test_file_backed_store_copies_artifact_content_addressed(tmp_path):
    source = tmp_path / "artifact.json"
    source.write_text('{"schema":"artifact/v1"}', encoding="utf-8")
    store = FileBackedHarnessStore(tmp_path / "store")

    artifact = store.copy_artifact(source, label="sample")

    assert artifact["schema"] == "harness.artifact/v1"
    assert artifact["sha256"]
    assert artifact["stored_path"].endswith(".json")
    assert len(read_jsonl(store.artifacts_path)) == 1
    assert store.snapshot()["artifact_rows"] == 1
    assert store.snapshot()["artifacts"] == 1


def test_file_backed_store_queries_artifacts_by_run_id(tmp_path):
    source_a = tmp_path / "a.json"
    source_b = tmp_path / "b.json"
    source_a.write_text('{"schema":"artifact/a"}', encoding="utf-8")
    source_b.write_text('{"schema":"artifact/b"}', encoding="utf-8")
    store = FileBackedHarnessStore(tmp_path / "store")

    store.copy_artifact(source_a, run_id="run_a", label="a")
    store.copy_artifact(source_b, run_id="run_b", label="b")
    store.copy_artifact(source_a, run_id="run_a", label="a-again")

    rows = store.artifacts_for_run("run_a")
    assert [row["label"] for row in rows] == ["a", "a-again"]
    assert all(row["run_id"] == "run_a" for row in rows)
