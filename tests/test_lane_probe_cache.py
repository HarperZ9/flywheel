"""The probe cache and the start probe.

The start probe spawns every lane once, so it runs only when the desktop
started the engine (``--desktop-launch``): never under ``flywheel up``, never
in the gateway tests, and never against an http lane unless network contact
at start is allowed (O-10 default: on request only).
"""
from __future__ import annotations

import json

from harness.lane_probe_cache import (SCHEMA, ProbeCache, lane_pin, outcome_from_row,
                                      probe_lanes, start_probe)
from harness.lanes_registry import LANES

ENGINE = "9.9.9"


def _cache(tmp_path, engine=ENGINE):
    return ProbeCache(tmp_path / "lane-probes.json", engine=engine,
                      clock=lambda: "2026-09-26T12:00:00Z")


def _status(calls):
    def fn(name, *, probe, timeout):
        calls.append((name, probe, timeout))
        return {"name": name, "status": "live", "detail": "ok", "tool_names": ["x"]}
    return fn


def test_no_start_probe_without_desktop_launch(tmp_path):
    calls = []
    assert start_probe(desktop_launch=False, cache=_cache(tmp_path),
                       status_fn=_status(calls), background=False) is None
    assert calls == []
    assert not (tmp_path / "lane-probes.json").exists()


def test_start_probe_skips_http_lanes_and_probes_the_rest(tmp_path):
    calls = []
    rows = start_probe(desktop_launch=True, cache=_cache(tmp_path),
                       status_fn=_status(calls), background=False)
    probed = {name for name, _probe, _timeout in calls}
    http = {name for name, lane in LANES.items() if lane.kind == "http"}
    assert http and not probed & http
    assert probed == set(LANES) - http == set(rows)
    assert all(probe is True and timeout == 20 for _n, probe, timeout in calls)


def test_start_probe_reaches_http_lanes_only_when_network_is_allowed(tmp_path):
    calls = []
    start_probe(desktop_launch=True, cache=_cache(tmp_path), status_fn=_status(calls),
                allow_network=True, background=False)
    assert "bulletin" in {name for name, *_ in calls}


def test_start_probe_runs_four_lanes_at_a_time(tmp_path):
    import threading
    import time
    lock, live, peak = threading.Lock(), [0], [0]

    def slow(name, *, probe, timeout):
        with lock:
            live[0] += 1
            peak[0] = max(peak[0], live[0])
        time.sleep(0.05)
        with lock:
            live[0] -= 1
        return {"name": name, "status": "live", "detail": "", "tool_names": []}

    probe_lanes(list(LANES)[:10], cache=_cache(tmp_path), status_fn=slow)
    assert peak[0] == 4


def test_one_lane_raising_does_not_stop_the_others(tmp_path, capsys):
    def flaky(name, *, probe, timeout):
        if name == "gather":
            raise RuntimeError("boom")
        return {"name": name, "status": "live", "detail": "", "tool_names": []}

    rows = probe_lanes(["gather", "crucible"], cache=_cache(tmp_path), status_fn=flaky)
    assert rows["crucible"]["status"] == "live"
    assert "lane probe: gather: RuntimeError" in capsys.readouterr().err


def test_records_key_on_engine_version_and_pin(tmp_path):
    cache = _cache(tmp_path)
    cache.record("gather", lane_pin("gather"), "answered", tools=["gather.docs"])
    assert cache.lookup("gather", lane_pin("gather"))[0]["tools"] == ["gather.docs"]
    assert cache.lookup("gather", "0.0.0-other-pin") == (None, False)
    assert _cache(tmp_path, engine="1.0.4").lookup("gather", lane_pin("gather")) == (None, False)


def test_fresh_only_for_the_session_that_wrote_it(tmp_path):
    cache = _cache(tmp_path)
    cache.record("gather", lane_pin("gather"), "answered")
    assert cache.lookup("gather", lane_pin("gather"))[1] is True
    record, fresh = _cache(tmp_path).lookup("gather", lane_pin("gather"))
    assert record is not None and fresh is False


def test_outcome_from_a_probed_row():
    assert outcome_from_row({"status": "live"}, http=False) == ("answered", "")
    assert outcome_from_row({"status": "stale"}, http=False) == (
        "unhealthy", "health_check_failed")
    failed = {"status": "declared",
              "detail": "MCP probe failed: runtime_executable_missing (cannot launch)"}
    assert outcome_from_row(failed, http=False) == (
        "cannot_launch", "runtime_executable_missing")
    assert outcome_from_row(failed, http=True) == ("unreachable", "network_error")
    assert outcome_from_row({"status": "missing",
                             "detail": "runtime selection failed: x"}, http=False) is None
    assert outcome_from_row({"status": "declared", "detail": "not probed"}, http=False) is None


def test_validated_keys_are_names_only(tmp_path):
    cache = _cache(tmp_path)
    cache.record_validated("forum", ["FORUM_KEY"])
    assert cache.validated("forum") == {"FORUM_KEY"}
    data = json.loads((tmp_path / "lane-probes.json").read_text(encoding="utf-8"))
    assert data["schema"] == SCHEMA and data["validated"] == {"forum": ["FORUM_KEY"]}


def test_a_corrupt_cache_file_reads_as_empty(tmp_path):
    (tmp_path / "lane-probes.json").write_text("{not json", encoding="utf-8")
    cache = _cache(tmp_path)
    assert cache.lookup("gather", lane_pin("gather")) == (None, False)
    cache.record("gather", lane_pin("gather"), "answered")
    assert cache.lookup("gather", lane_pin("gather"))[0]["outcome"] == "answered"


def test_the_gateway_starts_the_probe_only_with_the_flag(monkeypatch):
    """The one-line hook in gateway.main passes the flag through; the default
    (flywheel up, tests) is off."""
    from harness import gateway
    import harness.lane_probe_cache as probes
    seen = []
    monkeypatch.setattr(probes, "start_probe", lambda **kw: seen.append(kw))

    class _Server:
        server_address = ("127.0.0.1", 0)

    monkeypatch.setattr(gateway, "_bind_hosts", lambda hosts, port: [_Server()])
    monkeypatch.setattr(gateway, "_serve_all", lambda servers: None)
    # main() configures the handler class and one variable; restore both after.
    for name in ("root", "serve_url", "ollama_url", "run_root", "cors", "allowed_hosts",
                 "flywheel_home", "auth_token", "operation_service",
                 "operation_process_factory", "session_token_store",
                 "_session_token_state_root", "startup_recovery"):
        monkeypatch.setattr(gateway._Handler, name, getattr(gateway._Handler, name, None),
                            raising=False)
    monkeypatch.delenv("FLYWHEEL_LOCAL_AGENT_WORKSPACE", raising=False)
    assert gateway.main(["--port", "0"]) == 0
    assert gateway.main(["--port", "0", "--desktop-launch"]) == 0
    assert seen == [{"desktop_launch": False}, {"desktop_launch": True}]
