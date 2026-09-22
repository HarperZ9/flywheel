"""Independent attribution and missing-observation controls for live usage."""
import json

import pytest

from harness.usage_live import EndpointTelemetry, UsageLiveSampler
from tests.test_usage_live import _Clock
from tests.test_usage_route import _emit


def test_vllm_models_have_separate_counters_and_rate_baselines():
    clock = _Clock()
    samples = iter([
        'vllm:generation_tokens_total{model_name="a"} 10\n'
        'vllm:generation_tokens_total{model_name="b"} 30\n',
        'vllm:generation_tokens_total{model_name="b"} 50\n'
        'vllm:generation_tokens_total{model_name="a"} 14\n',
    ])
    sampler = UsageLiveSampler(get_text=lambda *_: next(samples),
        now_seconds=clock.seconds, now_utc=clock.utc)
    endpoint = EndpointTelemetry("vllm", "default", "http://127.0.0.1:8000", "test")
    first = sampler.snapshot([endpoint])["models"]
    assert {r["model"]: r["generated_tokens"] for r in first} == {"a": 10, "b": 30}
    clock.tick(2)
    second = sampler.snapshot([endpoint])["models"]
    assert {r["model"]: r["decode_tokens_per_second"] for r in second} == {"a": 2, "b": 10}


@pytest.mark.parametrize("label", ["/tmp/private/model", r"C:\private\model", "sk-secret"])
def test_metric_model_paths_do_not_leave_sampler(label):
    sampler = UsageLiveSampler(get_text=lambda *_:
        'vllm:generation_tokens_total{model_name="' + label + '"} 10\n')
    body = sampler.snapshot([EndpointTelemetry("vllm", "configured",
        "http://127.0.0.1:8000", "test")])
    assert label not in json.dumps(body)
    assert body["models"][0]["model"].startswith("model-")


def test_disconnect_requires_fresh_baseline():
    clock = _Clock()
    samples = iter([10, RuntimeError("endpoint unavailable"), 30, 40])
    def fetch(*_):
        value = next(samples)
        if isinstance(value, Exception):
            raise value
        return [{"id": 0, "id_task": 1, "n_decoded": value}]
    sampler = UsageLiveSampler(get_json=fetch, now_seconds=clock.seconds,
        now_utc=clock.utc)
    ep = EndpointTelemetry("llamacpp", "m", "http://127.0.0.1:8080", "test")
    sampler.snapshot([ep])
    clock.tick(1)
    assert sampler.snapshot([ep])["models"][0]["status"] == "unavailable"
    clock.tick(1)
    assert sampler.snapshot([ep])["models"][0]["decode_tokens_per_second"] is None
    clock.tick(1)
    assert sampler.snapshot([ep])["models"][0]["decode_tokens_per_second"] == 10


@pytest.mark.parametrize("slots", [[], [{"n_decoded": 10 ** 400}],
    [{"n_decoded": 1.5}], [{"n_decoded": 1}] * 17])
def test_invalid_or_incomplete_slot_population_is_not_measured(slots):
    sampler = UsageLiveSampler(get_json=lambda *_: slots)
    body = sampler.snapshot([EndpointTelemetry("llamacpp", "m",
        "http://127.0.0.1:8080", "test")])
    assert body["models"][0]["status"] == "unavailable"
    assert body["models"][0]["generated_tokens"] is None


@pytest.mark.parametrize("usage", [
    {"prompt": -1, "completion": 5, "total": 4},
    {"prompt": 1, "completion": 5, "total": 4},
    {"prompt": 2 ** 54, "completion": 0, "total": 2 ** 54},
])
def test_invalid_provider_counts_use_estimate_in_verifiable_receipt(tmp_path, usage):
    filename = _emit(tmp_path, "openai", "openai:gpt-4o-mini", "hello", usage)
    receipt = json.loads((tmp_path / "usage" / filename).read_text())
    assert receipt["source"] == "estimated"
    tokens = receipt["tokens"]
    assert int(tokens["total"]) == int(tokens["prompt"]) + int(tokens["completion"])
