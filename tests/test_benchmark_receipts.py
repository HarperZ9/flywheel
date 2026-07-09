from harness.benchmark_receipts import infer_benchmark_verdict, store_benchmark_outputs
from harness.file_backed_store import FileBackedHarnessStore, read_jsonl


def test_infer_benchmark_verdict_from_direct_passed_flag():
    assert infer_benchmark_verdict({"passed": True}) == "BENCHMARK_PASS"
    assert infer_benchmark_verdict({"passed": False}) == "BENCHMARK_FAIL"


def test_infer_benchmark_verdict_from_witness_gate():
    passing = {"summary": {"witness_gate": {"passed": True}}}
    failing = {"summary": {"witness_gate": {"passed": False}}}
    assert infer_benchmark_verdict(passing) == "BENCHMARK_GATE_PASS"
    assert infer_benchmark_verdict(failing) == "BENCHMARK_GATE_FAIL"


def test_store_benchmark_outputs_records_receipt_and_artifact(tmp_path):
    artifact = tmp_path / "scorecard.json"
    artifact.write_text('{"schema":"benchmark/v1"}', encoding="utf-8")
    store_root = tmp_path / "store"

    outputs = store_benchmark_outputs(
        {"schema": "benchmark/v1", "passed": True},
        store_root=str(store_root),
        kind="sample_benchmark",
        run_id="run_bench",
        artifact_paths=[(str(artifact), "scorecard-json")],
    )

    store = FileBackedHarnessStore(store_root)
    receipts = read_jsonl(store.receipts_path)
    assert outputs[0]["schema"] == "harness.receipt/v1"
    assert outputs[0]["kind"] == "sample_benchmark"
    assert outputs[0]["verdict"] == "BENCHMARK_PASS"
    assert outputs[1]["schema"] == "harness.artifact/v1"
    assert len(receipts) == 1


def test_store_benchmark_outputs_noops_without_store_root():
    outputs = store_benchmark_outputs(
        {"schema": "benchmark/v1", "passed": True},
        store_root="",
        kind="sample_benchmark",
    )

    assert outputs == []
