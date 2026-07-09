from harness.file_backed_store import FileBackedHarnessStore
from scripts.run_harness_store_query import query_store, render_markdown


def test_query_store_filters_receipts_events_and_artifacts_by_run_id(tmp_path):
    store = FileBackedHarnessStore(tmp_path / "store")
    run = store.create_run(kind="closed_loop_benchmark_seed", title="seed")
    other = store.create_run(kind="other", title="other")
    source = tmp_path / "artifact.json"
    source.write_text('{"schema":"artifact/v1"}', encoding="utf-8")
    store.put_receipt(kind="seed", body={"schema": "seed/v1"}, run_id=run["run_id"])
    store.copy_artifact(source, run_id=run["run_id"], label="seed-artifact")
    store.copy_artifact(source, run_id=other["run_id"], label="other-artifact")

    result = query_store(str(tmp_path / "store"), run_id=run["run_id"])

    assert result["schema"] == "harness.file-store-query/v1"
    assert result["summary"]["runs"] == 1
    assert result["summary"]["receipts"] == 1
    assert result["summary"]["artifacts"] == 1
    assert result["artifacts"][0]["label"] == "seed-artifact"


def test_render_markdown_includes_receipts_and_artifacts(tmp_path):
    store = FileBackedHarnessStore(tmp_path / "store")
    run = store.create_run(kind="closed_loop_benchmark_seed", title="seed")
    source = tmp_path / "artifact.json"
    source.write_text('{"schema":"artifact/v1"}', encoding="utf-8")
    store.put_receipt(kind="seed", body={"schema": "seed/v1"}, run_id=run["run_id"])
    store.copy_artifact(source, run_id=run["run_id"], label="seed-artifact")

    result = query_store(str(tmp_path / "store"), run_id=run["run_id"])
    markdown = render_markdown(result)

    assert "# Harness file-store query" in markdown
    assert "## Receipts" in markdown
    assert "## Artifacts" in markdown
    assert "seed-artifact" in markdown
