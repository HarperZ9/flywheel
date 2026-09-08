from harness.cross_harness_adapters import FlywheelRouterAdapter, LocalRouterAdapter, _clean
from harness.cross_harness_artifacts import canonical_sha256
from harness.cross_harness_executor import SHARED_TOOL_POLICY, execute_cross_harness_manifest, expand_attempt_rows
from harness.cross_harness_types import AdapterResult, AttemptRequest
from test_cross_harness_adapters import local_profile, request as adapter_request
from test_cross_harness_executor import FakeAdapter, _manifest, _one_task, _runtime


class CaptureAdapter(FakeAdapter):
    def execute(self, request):
        self.request_policy = dict(request.tool_policy)
        return super().execute(request)
class CaptureLocalRouter(CaptureAdapter):
    adapter_id = "openai_compatible_local/v1"
class FakeDirectCodex(CaptureAdapter):
    role = "codex_harness"
    adapter_id = "codex_cli_json/v1"
def _compact_request(tmp_path, role, adapter, model, requested):
    policy = {**SHARED_TOOL_POLICY, "max_steps": 9, "max_output_tokens": 64, "compact_budget": 220}
    return AttemptRequest(**{**adapter_request(tmp_path, role, adapter, model, requested).__dict__,
                            "tool_policy": policy, "tool_policy_sha256": canonical_sha256(policy)})
def _assert_numeric_compaction_receipt(result):
    receipt = result.resource_observation["last_compaction"]
    event = next(e["last_compaction"] for e in result.tool_trace if e.get("type") == "compaction")
    for view in (receipt, event):
        for key in ("token_budget", "tokens_before", "tokens_after", "budget_floor_tokens"):
            assert type(view[key]) is int


def test_compact_budget_changes_planned_tool_policy_identity(tmp_path):
    kwargs = dict(artifact_root=tmp_path, run_id="run", phase="spark",
                  selectors=["agt-001"], roles=["flywheel_harness"], repetitions=1)
    default = expand_attempt_rows(_manifest(["flywheel_harness"]),
                                  _runtime(["flywheel_harness"]), **kwargs)[0]
    compacted = expand_attempt_rows(_manifest(["flywheel_harness"]),
                                    _runtime(["flywheel_harness"]),
                                    compact_budget=900, **kwargs)[0]
    assert "compact_budget" not in default["tool_policy"]
    assert compacted["tool_policy"]["compact_budget"] == 900
    assert compacted["tool_policy_sha256"] == canonical_sha256(compacted["tool_policy"])
    assert compacted["tool_policy_sha256"] != default["tool_policy_sha256"]


def test_executed_row_promotes_compaction_receipt_to_metrics(tmp_path):
    source = tmp_path / "source"; source.mkdir()
    receipt = {"schema": "flywheel.compaction/v1", "method": "middle-fold", "budget_status": "fit"}
    result = AdapterResult("returned", '{"artifacts":{"result.json":{}}}',
                           [{"type": "compaction", "last_compaction": receipt}], 1, "14B",
                           "seeded", "", "", {"compact_budget": 900, "last_compaction": receipt}, {}, [], [],
                           "structured_provider_response")
    manifest = _one_task(source, expected=("result.json",), oracle={"expected_artifacts": ["result.json"]})
    manifest["provider_specs"][0]["adapter_id"] = "openai_compatible_local/v1"
    adapter = CaptureLocalRouter(result=result)
    run = execute_cross_harness_manifest(
        manifest, _runtime(["local_14b"]), {"local_14b": adapter},
        artifact_root=tmp_path / "artifacts", source_root=source, run_id="run", phase="local",
        selectors=["agt-001"], roles=["local_14b"], repetitions=1, compact_budget=900)
    metrics = run["rows"][0]["metrics"]
    assert adapter.request_policy["compact_budget"] == 900
    assert metrics["compact_budget_requested"] == 900
    assert metrics["compact_budget_control_state"] == "applied"
    assert metrics["compact_budget"] == 900
    assert metrics["last_compaction"] == receipt
    assert metrics["resource_observation"]["last_compaction"] == receipt


def test_direct_codex_compact_budget_request_is_not_reported_as_applied(tmp_path):
    source = tmp_path / "source"; source.mkdir()
    unsupported = {"compact_budget": 900, "last_compaction": {"method": "middle-fold"}}
    result = AdapterResult("returned", '{"artifacts":{"result.json":{}}}', [], 1,
                           "spark", "unsupported", "", "", unsupported, {}, [], [],
                           "structured_provider_event")
    manifest = _one_task(source, expected=("result.json",), oracle={"expected_artifacts": ["result.json"]})
    manifest["provider_specs"][0].update(provider_role="codex_harness", harness_id="codex",
                                         adapter_id="codex_cli_json/v1", model_id="spark",
                                         requested_model_reference="spark")
    adapter = FakeDirectCodex(result=result)
    run = execute_cross_harness_manifest(
        manifest, _runtime(["codex_harness"]), {"codex_harness": adapter},
        artifact_root=tmp_path / "artifacts", source_root=source, run_id="run", phase="spark",
        selectors=["agt-001"], roles=["codex_harness"], repetitions=1, compact_budget=900)
    metrics = run["rows"][0]["metrics"]
    assert adapter.request_policy["compact_budget"] == 900
    assert metrics["compact_budget_requested"] == 900
    assert metrics["compact_budget_control_state"] == "unsupported_adapter"
    assert metrics["compact_budget_reported_unsupported"] == 900
    assert metrics["last_compaction_reported_unsupported"] == unsupported["last_compaction"]
    assert "compact_budget" not in metrics
    assert "last_compaction" not in metrics


def test_flywheel_router_sanitized_last_compaction_keeps_numeric_receipt_fields(tmp_path):
    (tmp_path / "x").write_text("evidence " * 120, encoding="utf-8")
    class Proposer:
        model_ref = "spark"
        def __init__(self): self.calls = 0
        def generate(self, *a, **k):
            self.calls += 1
            return type("Out", (), {"text": 'TOOL read_file {"path":"x"}' if self.calls < 9 else "done",
                                    "model_ref": "spark", "usage": None, "served_model": ""})()
    result = FlywheelRouterAdapter(proposer=Proposer(), proposer_invocations_max=None).execute(
        _compact_request(tmp_path, "flywheel_harness", "flywheel_router/v1", "spark", "spark"))
    assert result.execution_state == "returned"; _assert_numeric_compaction_receipt(result)


def test_local_router_sanitized_last_compaction_keeps_numeric_receipt_fields(tmp_path):
    (tmp_path / "x").write_text("evidence " * 120, encoding="utf-8")
    class Backend:
        name = "serve"
        def __init__(self): self.calls = 0
        def chat(self, messages, **kwargs):
            self.calls += 1
            return {"text": 'TOOL read_file {"path":"x"}' if self.calls < 9 else "done",
                    "model_ref": "local:14b", "seed": kwargs["seed"]}
    result = LocalRouterAdapter("local_14b", local_profile(), backend_factory=lambda p, t: Backend()).execute(
        _compact_request(tmp_path, "local_14b", "openai_compatible_local/v1", "flywheel-local-coder-14b", "local:14b"))
    assert result.execution_state == "returned"; _assert_numeric_compaction_receipt(result)


def test_compaction_receipt_sanitizer_allows_only_schema_numeric_fields():
    receipt = {"schema": "flywheel.compaction/v1", "token_budget": 220, "tokens_before": 500,
               "tokens_after": 199, "budget_floor_tokens": 150, "api_token": "canary-secret"}
    clean = _clean({"last_compaction": receipt, "token_budget": 220, "nested": {"tokens_after": 1}})
    assert clean["last_compaction"]["token_budget"] == 220
    assert clean["last_compaction"]["api_token"] == "[REDACTED]"
    assert clean["token_budget"] == "[REDACTED]"
    assert clean["nested"]["tokens_after"] == "[REDACTED]"
    bad = _clean({"schema": "flywheel.compaction/v1", "token_budget": "220",
                  "tokens_before": True, "tokens_after": -1, "budget_floor_tokens": 3.0})
    assert {bad[k] for k in ("token_budget", "tokens_before", "tokens_after", "budget_floor_tokens")} == {"[REDACTED]"}
