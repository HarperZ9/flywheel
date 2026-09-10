"""Real runner/factory wiring with an injected local backend, never a model."""
import json
import hashlib
from types import SimpleNamespace

from harness.local_agent import OllamaBackend
from harness.local_finalizer_experiment import FIXED_PARAMS, run_candidate_prefix_experiment
from scripts.run_local_finalizer_candidate_prefix_experiment import build_candidate_runner
from test_local_finalizer_accounting import task
from harness.local_finalizer_accounting import ExperimentAccounting


def test_real_runner_preserves_requests_and_counts_through_cli_factory(tmp_path):
    requests = []
    class Adapter:
        role, adapter_id = "local_14b", "fake"
        profile = {"profile_id": "fake", "model_ref": "qwen", "endpoint_url": "http://127.0.0.1:1",
            "backend": "ollama", "num_ctx": 32768, "structured_final_output": {
                "state": "supported", "transport": "ollama_chat_format_json_schema"}}

        def availability(self, request):
            return SimpleNamespace(available=True)

        def backend_factory(self, profile, timeout):
            def transport(method, url, body, timeout):
                decoded = json.loads(body)
                requests.append(decoded)
                return 200, {"model": "qwen", "message": {"content": '{"artifacts":{}}'},
                    "done": True, "done_reason": "stop", "eval_count": 7}
            return OllamaBackend(base_url=profile["endpoint_url"], model="qwen", transport=transport)

    item = {**task(), "prompt": "Return the artifact envelope.", "oracle": {}, "visible_input_sha256s": {}}
    source = tmp_path / "source"
    source.mkdir()
    sentinel = source / "historical.json"
    sentinel.write_bytes(b'{"legacy":8}\n')
    summaries = []
    for enabled in (False, True):
        runner, context = build_candidate_runner(Adapter(), source, FIXED_PARAMS,
                                                  record_invocations=enabled)
        assert runner.accounting is context
        summary = run_candidate_prefix_experiment([item], tmp_path / str(enabled), FIXED_PARAMS,
            candidate_runner=runner.candidate, finalizer_runner=runner.finalizer,
            score_runner=lambda *args: ("pass", []), accounting=context)
        summaries.append(summary)
    assert requests[:3] == requests[3:]
    assert "invocation_accounting" not in summaries[0]
    counts = summaries[1]["invocation_accounting"]
    assert counts["total_started_invocations"] == 3
    assert counts["normal_started_invocations"] == 1
    assert counts["finalizer_started_invocations"] == 2
    assert counts["native_usage"]["eval_count"]["total"] == 21
    assert counts["request_send_attempts"] is None
    assert sentinel.read_bytes() == b'{"legacy":8}\n'
    assert [r["oracle_state"] for r in summaries[0]["rows"]] == [r["oracle_state"] for r in summaries[1]["rows"]]


def test_manifest_bindings_distinguish_fixture_and_execution_source(tmp_path, monkeypatch):
    import scripts.run_local_finalizer_candidate_prefix_experiment as cli
    fixture = tmp_path / "fixtures"
    fixture.mkdir()
    task_set, contract = tmp_path / "tasks.json", tmp_path / "contract.json"
    task_set.write_bytes(b'{"tasks":[]}')
    contract.write_bytes(b'{"contract":1}')
    monkeypatch.setattr(cli, "_source_revision", lambda root: "a" * 40 if root == fixture else "b" * 40)
    adapter = SimpleNamespace(profile={"profile_id": "local-test", "model_ref": "qwen:14b",
                                      "profile_sha256": "c" * 64, "secret": "never retained"})
    _, context = build_candidate_runner(adapter, fixture, FIXED_PARAMS, record_invocations=True,
                                         task_set_path=task_set, contract_path=contract)
    context.prepare(tmp_path / "receipts", [task()], FIXED_PARAMS, "d" * 64)
    bindings = context.manifest["bindings"]
    assert bindings["fixture_source_head"] == "a" * 40
    assert bindings["execution_source_head"] == "b" * 40
    assert bindings["task_set_sha256"] == hashlib.sha256(task_set.read_bytes()).hexdigest()
    assert bindings["contract_sha256"] == hashlib.sha256(contract.read_bytes()).hexdigest()
    assert bindings["profile_id"] == "local-test" and bindings["model_ref"] == "qwen:14b"
    assert "never retained" not in json.dumps(context.manifest)
    unknown = ExperimentAccounting()
    unknown.prepare(tmp_path / "unknown", [task()], FIXED_PARAMS, "d" * 64)
    assert all(value is None for value in unknown.manifest["bindings"].values())
    unsafe = ExperimentAccounting(bindings={"profile_id": "private\ntext", "model_ref": "https://secret",
                                           "profile_sha256": "not a hash", "execution_source_dirty": "false"})
    assert all(value is None for value in unsafe.bindings.values())
