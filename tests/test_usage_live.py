import io
import json
from datetime import datetime, timezone

from harness import gateway, usage_live
from harness.gateway_custody import is_private
from harness.usage_live import EndpointTelemetry, UsageLiveSampler


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def tick(self, seconds):
        self.now += seconds

    def seconds(self):
        return self.now

    def utc(self):
        return datetime.fromtimestamp(self.now, timezone.utc)


class _Headers:
    def __init__(self, cl="0"):
        self._cl = cl

    def get(self, key, default=None):
        return self._cl if key == "Content-Length" else default


def _get(path, run_root):
    h = gateway._Handler.__new__(gateway._Handler)
    h.path = path
    h.root = "."
    h.run_root = str(run_root)
    h.headers = _Headers()
    h.rfile = io.BytesIO(b"")
    sent = {}
    h._json = lambda b, code=200: sent.update(body=b, code=code)
    h._get()
    return sent


def test_llamacpp_slots_need_two_samples_before_reporting_live_rates():
    clock = _Clock()
    slots = [
        [{"id": 0, "id_task": 7, "next_token": {"n_decoded": 10},
          "n_prompt_tokens_processed": 20}],
        [{"id": 0, "id_task": 7, "next_token": {"n_decoded": 30},
          "n_prompt_tokens_processed": 50}],
    ]

    def get_json(url, timeout, byte_limit):
        assert url == "http://127.0.0.1:8080/slots"
        return slots.pop(0)

    sampler = UsageLiveSampler(
        get_json=get_json, now_seconds=clock.seconds, now_utc=clock.utc)
    endpoint = EndpointTelemetry(
        endpoint="llamacpp", model="served-model",
        base_url="http://127.0.0.1:8080/v1", source="fixture")

    first = sampler.snapshot([endpoint])["models"][0]
    assert first["status"] == "warming_up"
    assert first["decode_tokens_per_second"] is None
    assert first["counter_scope"] == "current_request"
    assert first["generated_tokens"] == 10

    clock.tick(2.0)
    second = sampler.snapshot([endpoint])["models"][0]
    assert second["status"] == "observed"
    assert second["decode_tokens_per_second"] == 10.0
    assert second["prefill_tokens_per_second"] == 15.0
    assert second["generated_tokens"] == 30
    assert second["prompt_tokens"] == 50
    assert second["report_denominator"]["seconds"] == 2.0


def test_counter_reset_or_invalid_counters_never_create_false_rates():
    clock = _Clock()
    samples = [
        [{"id": 0, "id_task": 1, "next_token": {"n_decoded": 20},
          "n_prompt_tokens_processed": 5}],
        [{"id": 0, "id_task": 2, "next_token": {"n_decoded": 2},
          "n_prompt_tokens_processed": 1}],
        [{"id": 0, "id_task": 2, "next_token": {"n_decoded": True},
          "n_prompt_tokens_processed": -1}],
    ]

    sampler = UsageLiveSampler(
        get_json=lambda *_args: samples.pop(0),
        now_seconds=clock.seconds, now_utc=clock.utc)
    endpoint = EndpointTelemetry(
        endpoint="llamacpp", model="served-model",
        base_url="http://127.0.0.1:8080/v1", source="fixture")

    assert sampler.snapshot([endpoint])["models"][0]["status"] == "warming_up"
    clock.tick(1.0)
    reset = sampler.snapshot([endpoint])["models"][0]
    assert reset["status"] == "warming_up"
    assert reset["decode_tokens_per_second"] is None
    assert reset["reason"] == "runtime counters reset or task changed"

    clock.tick(1.0)
    invalid = sampler.snapshot([endpoint])["models"][0]
    assert invalid["status"] == "unavailable"
    assert invalid["reason"] == "invalid runtime counters"
    assert invalid["generated_tokens"] is None


def test_missing_llamacpp_prompt_counter_still_reports_decode_with_prompt_null():
    clock = _Clock()
    samples = [
        [{"id": 0, "id_task": 1, "next_token": {"n_decoded": 12}}],
        [{"id": 0, "id_task": 1, "next_token": {"n_decoded": 32}}],
    ]
    sampler = UsageLiveSampler(get_json=lambda *_args: samples.pop(0),
                               now_seconds=clock.seconds, now_utc=clock.utc)
    endpoint = EndpointTelemetry(
        endpoint="llamacpp", model="served-model",
        base_url="http://127.0.0.1:8080/v1", source="fixture")

    first = sampler.snapshot([endpoint])["models"][0]
    assert first["status"] == "warming_up"
    assert first["prompt_tokens"] is None
    assert first["reason"] == "Prompt-processing counter not reported"
    clock.tick(2.0)
    second = sampler.snapshot([endpoint])["models"][0]
    assert second["status"] == "observed"
    assert second["decode_tokens_per_second"] == 10.0
    assert second["prefill_tokens_per_second"] is None
    assert second["prompt_tokens"] is None
    assert second["reason"] == "Prompt-processing counter not reported"


def test_invalid_present_llamacpp_prompt_counter_is_unavailable():
    sampler = UsageLiveSampler(get_json=lambda *_args: [
        {"id": 0, "id_task": 1, "next_token": {"n_decoded": 12},
         "n_prompt_tokens_processed": True}])
    endpoint = EndpointTelemetry(
        endpoint="llamacpp", model="served-model",
        base_url="http://127.0.0.1:8080/v1", source="fixture")

    model = sampler.snapshot([endpoint])["models"][0]
    assert model["status"] == "unavailable"
    assert model["reason"] == "invalid runtime counters"
    assert model["generated_tokens"] is None


def test_partial_vllm_metric_stream_reports_decode_with_prefill_null():
    clock = _Clock()
    samples = iter([
        'vllm:generation_tokens_total 12\n',
        'vllm:generation_tokens_total 32\n',
    ])
    sampler = UsageLiveSampler(get_text=lambda *_args:
                               next(samples),
                               now_seconds=clock.seconds, now_utc=clock.utc)
    endpoint = EndpointTelemetry(
        endpoint="vllm", model="served-model",
        base_url="http://127.0.0.1:8000/v1", source="fixture")

    assert sampler.snapshot([endpoint])["models"][0]["status"] == "warming_up"
    clock.tick(4.0)
    model = sampler.snapshot([endpoint])["models"][0]
    assert model["status"] == "observed"
    assert model["decode_tokens_per_second"] == 5.0
    assert model["prefill_tokens_per_second"] is None
    assert model["prompt_tokens"] is None
    assert model["reason"] == "Prompt-processing counter not reported"


def test_endpoint_url_change_starts_a_new_baseline():
    clock = _Clock()
    sampler = UsageLiveSampler(
        get_json=lambda *_args: [{"id": 0, "id_task": 1,
                                  "next_token": {"n_decoded": 20},
                                  "n_prompt_tokens_processed": 4}],
        now_seconds=clock.seconds, now_utc=clock.utc)
    first = EndpointTelemetry("llamacpp", "m", "http://127.0.0.1:8080/v1", "fixture")
    moved = EndpointTelemetry("llamacpp", "m", "http://127.0.0.1:18080/v1", "fixture")

    assert sampler.snapshot([first])["models"][0]["status"] == "warming_up"
    clock.tick(1.0)
    model = sampler.snapshot([moved])["models"][0]
    assert model["status"] == "warming_up"
    assert model["reason"] == "collecting baseline"


def test_unsupported_or_nonliteral_local_endpoint_is_unavailable_without_fetch():
    calls = []
    sampler = UsageLiveSampler(get_json=lambda *_args: calls.append("fetch") or [])
    rows = [
        EndpointTelemetry("ollama", "m", "http://127.0.0.1:11434/v1", "fixture"),
        EndpointTelemetry("llamacpp", "m", "http://localhost:8080/v1", "fixture"),
    ]

    body = sampler.snapshot(rows)
    assert [m["status"] for m in body["models"]] == ["unavailable", "unavailable"]
    assert body["models"][0]["reason"] == "live telemetry unsupported for endpoint"
    assert body["models"][1]["reason"] == "endpoint is not a literal loopback URL"
    assert calls == []


def test_vllm_redirect_refusal_is_reported_without_rates():
    def get_text(url, timeout, byte_limit):
        raise RuntimeError("redirect refused")

    sampler = UsageLiveSampler(get_text=get_text)
    endpoint = EndpointTelemetry(
        endpoint="vllm", model="served-model",
        base_url="http://127.0.0.1:8000/v1", source="fixture")

    model = sampler.snapshot([endpoint])["models"][0]
    assert model["status"] == "unavailable"
    assert model["reason"] == "redirect refused"
    assert model["decode_tokens_per_second"] is None


def test_gateway_dispatches_private_usage_live_without_changing_summary(tmp_path, monkeypatch):
    assert is_private("/api/usage/live") is True
    assert is_private("/api/usage") is False

    class _FakeSampler:
        def snapshot(self, endpoints=None):
            assert endpoints == []
            return {"schema": "flywheel.usage-live/v1", "models": []}

    monkeypatch.setattr(usage_live, "_LIVE_SAMPLER", _FakeSampler())
    live = _get("/api/usage/live", tmp_path)
    assert live["code"] == 200
    assert live["body"] == {"schema": "flywheel.usage-live/v1", "models": []}

    summary = _get("/api/usage", tmp_path)
    assert summary["code"] == 200
    assert summary["body"]["schema"] == "flywheel.usage-summary/v1"


def test_live_payload_has_no_prompts_paths_commands_or_non_json_numbers():
    clock = _Clock()
    metrics = "\n".join([
        'vllm:prompt_tokens_total{model_name="safe-model"} 6',
        'vllm:generation_tokens_total{model_name="safe-model"} 10',
    ])
    sampler = UsageLiveSampler(
        get_text=lambda *_args: metrics, now_seconds=clock.seconds,
        now_utc=clock.utc)
    endpoint = EndpointTelemetry(
        endpoint="vllm", model="served-model",
        base_url="http://127.0.0.1:8000/v1", source="fixture")

    body = sampler.snapshot([endpoint])
    dumped = json.dumps(body, allow_nan=False)
    assert "prompt text" not in dumped
    assert "command" not in dumped.lower()
    assert "C:" not in dumped and "/tmp/" not in dumped
    assert body["models"][0]["status"] == "warming_up"
    assert body["models"][0]["model"] == "safe-model"
