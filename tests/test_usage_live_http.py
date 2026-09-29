import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from harness import gateway, usage_live


def test_private_usage_live_http_requires_bearer_and_returns_body(tmp_path, monkeypatch):
    token = "usage-live-token"
    seen = []

    class _FakeSampler:
        def snapshot(self, endpoints=None):
            seen.append(endpoints)
            return {"schema": "flywheel.usage-live/v1",
                    "observed_utc": "2026-09-17T00:00:00+00:00",
                    "models": [{"id": "vllm:m", "model": "m", "endpoint": "vllm",
                                "status": "warming_up", "source": "vllm.prometheus",
                                "counter_scope": "current_runtime",
                                "decode_tokens_per_second": None,
                                "prefill_tokens_per_second": None,
                                "generated_tokens": 3, "prompt_tokens": 2,
                                "reason": "collecting baseline",
                                "report_denominator": {
                                    "kind": "live_poll_delta_seconds",
                                    "seconds": None,
                                    "last_observed_utc": "2026-09-17T00:00:00+00:00"}}]}

    class Handler(gateway._Handler):
        pass

    monkeypatch.setattr(usage_live, "_LIVE_SAMPLER", _FakeSampler())
    Handler.auth_token = token
    Handler.root = tmp_path
    Handler.run_root = str(tmp_path)
    Handler.flywheel_home = tmp_path / "home"
    Handler.allowed_hosts = gateway.DEFAULT_HOSTS
    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{http.server_address[1]}/api/usage/live"
    selected = (url + "?endpoint=vllm&model=m"
                "&base_url=http%3A%2F%2F127.0.0.1%3A65000%2Fv1")
    try:
        for headers in ({}, {"Authorization": "Bearer wrong"}):
            req = urllib.request.Request(url, headers=headers)
            try:
                urllib.request.urlopen(req, timeout=2)
            except urllib.error.HTTPError as exc:
                assert exc.code == 401
            else:
                raise AssertionError("private live usage route admitted bad auth")
        req = urllib.request.Request(selected,
                                     headers={"Authorization": "Bearer " + token})
        with urllib.request.urlopen(req, timeout=2) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        assert resp.status == 200
        assert body["schema"] == "flywheel.usage-live/v1"
        assert body["models"][0]["counter_scope"] == "current_runtime"
        assert seen[0][0].endpoint == "vllm"
        assert seen[0][0].model == "m"
        assert seen[0][0].base_url == "http://127.0.0.1:65000/v1"
    finally:
        http.shutdown()
        http.server_close()
        thread.join(timeout=2)
