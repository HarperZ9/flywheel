"""Independent attribution and missing-observation controls for live usage."""
import json

import pytest

from harness.usage_live import EndpointTelemetry, UsageLiveSampler
from tests.test_usage_live import _Clock


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


@pytest.mark.parametrize("base", ["http://127.0.0.1:bad",
    "http://127.0.0.1:65536", "http://127.0.0.1:-1"])
def test_invalid_port_is_unavailable_without_opening_a_connection(base):
    calls = []
    sampler = UsageLiveSampler(get_text=lambda *_: calls.append("fetch"))
    body = sampler.snapshot([EndpointTelemetry("vllm", "m", base, "test")])
    assert calls == []
    assert body["models"][0]["status"] == "unavailable"
    assert body["models"][0]["decode_tokens_per_second"] is None


def test_model_missing_from_valid_batch_requires_a_fresh_baseline():
    clock = _Clock()
    samples = iter([
        'vllm:generation_tokens_total{model_name="a"} 10\n'
        'vllm:generation_tokens_total{model_name="b"} 20\n',
        'vllm:generation_tokens_total{model_name="b"} 21\n',
        'vllm:generation_tokens_total{model_name="a"} 50\n'
        'vllm:generation_tokens_total{model_name="b"} 22\n',
    ])
    sampler = UsageLiveSampler(get_text=lambda *_: next(samples),
        now_seconds=clock.seconds, now_utc=clock.utc)
    ep = EndpointTelemetry("vllm", "default", "http://127.0.0.1:8000", "test")
    sampler.snapshot([ep])
    clock.tick(1)
    sampler.snapshot([ep])
    clock.tick(1)
    rows = {r["model"]: r for r in sampler.snapshot([ep])["models"]}
    assert rows["a"]["status"] == "warming_up"
    assert rows["a"]["decode_tokens_per_second"] is None
    assert rows["b"]["decode_tokens_per_second"] == 1


def test_positive_submillisecond_interval_is_not_reported_as_zero():
    clock = _Clock()
    counts = iter([1, 2])
    sampler = UsageLiveSampler(get_json=lambda *_: [
        {"id": 0, "id_task": 1, "n_decoded": next(counts)}],
        now_seconds=clock.seconds, now_utc=clock.utc)
    ep = EndpointTelemetry("llamacpp", "m", "http://127.0.0.1:8080", "test")
    sampler.snapshot([ep])
    clock.tick(0.0001)
    row = sampler.snapshot([ep])["models"][0]
    seconds = row["report_denominator"]["seconds"]
    assert seconds == pytest.approx(0.0001)
    assert seconds * row["decode_tokens_per_second"] == pytest.approx(1)


@pytest.mark.parametrize("metrics", ["vllm:generation_tokens_total ",
    "vllm:generation_tokens_total\t", "vllm:generation_tokens_total\n"])
def test_counter_without_value_is_unavailable(metrics):
    sampler = UsageLiveSampler(get_text=lambda *_: metrics)
    row = sampler.snapshot([EndpointTelemetry("vllm", "m",
        "http://127.0.0.1:8000", "test")])["models"][0]
    assert row["status"] == "unavailable"
    assert row["generated_tokens"] is None


def test_whitespace_lines_and_tab_separator_do_not_hide_valid_counters():
    sampler = UsageLiveSampler(get_text=lambda *_:
        ' \n\t\nother_metric \nvllm:generation_tokens_total\t7\n')
    row = sampler.snapshot([EndpointTelemetry("vllm", "m",
        "http://127.0.0.1:8000", "test")])["models"][0]
    assert row["status"] == "warming_up"
    assert row["generated_tokens"] == 7
