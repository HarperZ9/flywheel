"""Healthy server-loop shutdown, without a brittle elapsed-time assertion."""
from __future__ import annotations

import threading

from tests.enterprise_envs.package_helpers import add_product_src


def test_both_runtime_servers_poll_responsively_and_close_after_real_requests(
    tmp_path, monkeypatch,
):
    """Catches default-poll drift and leaked listeners or owned server loops."""
    add_product_src()
    from harness.enterprise_envs.http_client import request_json
    from service_desk_incident_env.v1.http_runtime import ServiceDeskRuntime
    from service_desk_incident_env.v1 import http_runtime

    observed = []
    lock = threading.Lock()
    both_started = threading.Event()
    original = http_runtime.ThreadingHTTPServer.serve_forever

    def observe_loop(server, poll_interval=0.5):
        with lock:
            observed.append((server, poll_interval))
            if len(observed) == 2:
                both_started.set()
        return original(server, poll_interval=poll_interval)

    monkeypatch.setattr(http_runtime.ThreadingHTTPServer, "serve_forever", observe_loop)
    runtime = ServiceDeskRuntime(tmp_path / "runtime", "run_lifecycle", "instance_lifecycle")
    runtime.start()
    servers = (runtime._agent_server, runtime._control_server)
    threads = tuple(runtime._threads)
    try:
        assert both_started.wait(5), "Both real server loops must start"
        agent = request_json(
            "GET", f"{runtime.agent_base_url}/api/now/table/incident",
            headers=runtime.runtime_agent_headers(), expect_status=200,
        )
        control = request_json(
            "GET", f"{runtime.control_base_url}/control/state",
            headers=runtime.runtime_control_headers(), expect_status=200,
        )
        hidden = request_json(
            "GET", f"{runtime.agent_base_url}/control/state",
            headers=runtime.runtime_agent_headers(), expect_status=404,
        )
        assert (agent["status"], control["status"], hidden["status"]) == (200, 200, 404)
    finally:
        runtime.stop()

    assert len(threads) == 2 and all(not thread.is_alive() for thread in threads)
    assert all(server.socket.fileno() == -1 for server in servers)
    assert runtime._threads == []
    assert runtime._agent_server is None and runtime._control_server is None
    runtime.stop()  # Closing an already stopped healthy runtime remains safe.
    assert {server for server, _ in observed} == set(servers)
    assert len(observed) == 2
    assert all(interval == 0.05 for _, interval in observed)
