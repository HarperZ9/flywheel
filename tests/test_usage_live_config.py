from harness import usage_live
from harness.usage_live import UsageLiveSampler
from harness.usage_live_config import resolve_usage_live_endpoints
from harness.usage_route import handle_usage_get


def test_no_live_selection_resolves_no_endpoints_and_polls_nothing():
    calls = []
    sampler = UsageLiveSampler(
        get_json=lambda *_: calls.append("json"),
        get_text=lambda *_: calls.append("text"))

    body = sampler.snapshot(resolve_usage_live_endpoints(""))

    assert body["models"] == []
    assert calls == []


def test_route_passes_empty_selection_to_sampler_without_static_discovery(tmp_path, monkeypatch):
    seen = []

    class FakeSampler:
        def snapshot(self, endpoints=None):
            seen.append(endpoints)
            return {"schema": "flywheel.usage-live/v1", "models": []}

    monkeypatch.setattr(usage_live, "_LIVE_SAMPLER", FakeSampler())

    body, code = handle_usage_get("/api/usage/live", "", tmp_path)

    assert code == 200
    assert body["models"] == []
    assert seen == [[]]


def test_explicit_vllm_selection_uses_that_url_and_model_without_fallback():
    urls = []

    def get_text(url, *_):
        urls.append(url)
        raise RuntimeError("endpoint unavailable")

    rows = resolve_usage_live_endpoints(
        "endpoint=vllm&model=chosen-model&base_url=http%3A%2F%2F127.0.0.1%3A65000%2Fv1")
    sampler = UsageLiveSampler(get_text=get_text)

    body = sampler.snapshot(rows)

    assert urls == ["http://127.0.0.1:65000/metrics"]
    assert body["models"][0]["endpoint"] == "vllm"
    assert body["models"][0]["model"] == "chosen-model"
    assert body["models"][0]["status"] == "unavailable"
    assert body["models"][0]["reason"] == "endpoint unavailable"


def test_endpoint_default_url_requires_explicit_endpoint_selection():
    none = resolve_usage_live_endpoints("")
    selected = resolve_usage_live_endpoints("endpoint=vllm&model=chosen-model")

    assert none == []
    assert len(selected) == 1
    assert selected[0].endpoint == "vllm"
    assert selected[0].model == "chosen-model"
    assert selected[0].base_url == "http://127.0.0.1:8000/v1"
    assert selected[0].source == "query.endpoint_default_url"


def test_unsupported_selected_endpoint_reports_unavailable_without_fetch():
    calls = []
    rows = resolve_usage_live_endpoints("endpoint=ollama&model=llama-local")
    sampler = UsageLiveSampler(get_json=lambda *_: calls.append("fetch"))

    body = sampler.snapshot(rows)

    assert calls == []
    assert body["models"][0]["endpoint"] == "ollama"
    assert body["models"][0]["status"] == "unavailable"
    assert body["models"][0]["reason"] == "live telemetry unsupported for endpoint"
