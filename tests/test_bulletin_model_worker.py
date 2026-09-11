"""One-shot worker controls use fake responses, never configured model ports."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from harness.bulletin_model_exchange import PrivateExchange
from harness.evidence_json import canonical_bytes
from harness.bulletin_model_worker import WorkerError, run_worker, supervise_generation


def request(stage="readiness", origin="http://127.0.0.1:9999"):
    return {"schema_version": 1, "run_id": "run", "reservation_id": f"run-{stage}",
            "stage_id": stage, "profile": {"profile_id": "fixture", "backend": "ollama",
            "endpoint_url": origin, "selectors": ["fixture"], "model_ref": "ollama:fixture",
            "expected_ollama_digest": "sha256:" + "a" * 64,
            "generation_config": {"num_ctx": 4096}}, "system": "", "messages": [
                {"role": "user", "content": "Synthetic bounded gate."}], "seed": 101,
            "temperature": 0.0 if stage == "readiness" else 0.2,
            "max_tokens": 32 if stage == "readiness" else 256 if stage == "smoke" else 512,
            "timeout_seconds": 2.0}


def reservation(req):
    return {"schema": "flywheel.bulletin-model-ledger/v1", "kind": "generation_reserved",
            "ordinal": 1, "run_id": req["run_id"], "reservation_id": req["reservation_id"],
            "stage_id": req["stage_id"], "max_tokens": req["max_tokens"]}


def fixture_factory(calls, *, text="received", model="fixture", digest="a" * 64):
    def factory(policy, *, observer):
        def send(method, url, body, timeout):
            calls.append((method, url, body, timeout))
            # These schema-shaped events are fake transport controls, not actual I/O.
            base = {"attempt_id": "aaaaaaaa-aaaa-4aaa-8aaa-" + ("aaaaaaaaaaaa" if method == "GET" else "bbbbbbbbbbbb"), "method": method,
                    "path": "/api/tags" if method == "GET" else "/api/chat"}
            for phase, connected, sent in [("connection_attempt", False, False),
                    ("request_send_started", True, False), ("terminal", True, True)]:
                observer({**base, "phase": phase, "connection_started": connected,
                    "request_send_started": sent, "outcome": "response" if phase == "terminal" else None,
                    "code": "response_received" if phase == "terminal" else None,
                    "status": 200 if phase == "terminal" else None})
            if method == "GET":
                return 200, {"models": [{"name": "fixture", "digest": digest}]}
            return 200, {"model": model, "message": {"content": text}, "eval_count": 3}
        return send
    return factory


@pytest.mark.parametrize("stage,methods", [("readiness", ["GET", "POST"]),
    ("smoke", ["POST"]), ("s01-p1", ["POST"])])
def test_real_gate_or_backend_exact_once(tmp_path, stage, methods):
    req, calls = request(stage), []
    with PrivateExchange.create(tmp_path / "invocation") as store:
        result = run_worker(req, store, reservation(req), transport_factory=fixture_factory(calls))
        assert result["backend_valid"] and result["text"] == "received"
        assert [row[0] for row in calls] == methods
        body = json.loads(calls[-1][2])
        assert body["options"]["num_predict"] == req["max_tokens"]
        assert body["options"]["num_ctx"] == 4096
        assert store.read("assistant.txt", max_bytes=100) == b"received"
        event = json.loads(store.read("transport-000.json", max_bytes=4096))
        assert event["reservation_id"] == req["reservation_id"]
        assert event["event"]["phase"] == "connection_attempt"
        assert event["event"]["request_send_started"] is False


@pytest.mark.parametrize("change", [{"max_tokens": True}, {"max_tokens": 33},
    {"stage_id": "unknown"}, {"temperature": float("nan")}, {"extra": 1}])
def test_invalid_request_never_constructs_transport(tmp_path, change):
    req = {**request(), **change}
    with PrivateExchange.create(tmp_path / "invocation") as store:
        with pytest.raises(WorkerError):
            run_worker(req, store, reservation(req), transport_factory=lambda *a, **k: pytest.fail("I/O"))


def test_real_readiness_failure_no_generation_and_capture_survives_identity_failure(tmp_path):
    for stage, digest, model in [("readiness", "b" * 64, "fixture"), ("smoke", "a" * 64, "other")]:
        req, calls = request(stage), []
        with PrivateExchange.create(tmp_path / stage) as store:
            result = run_worker(req, store, reservation(req),
                transport_factory=fixture_factory(calls, digest=digest, model=model))
            assert result["backend_valid"] is False
            assert len(calls) == 1
            if stage == "smoke":
                assert store.read("assistant.txt", max_bytes=100) == b"received"


def test_missing_reservation_denies_before_launch(tmp_path):
    req = request()
    with PrivateExchange.create(tmp_path / "ledger") as ledger, PrivateExchange.create(tmp_path / "call") as store:
        with pytest.raises(WorkerError):
            supervise_generation(req, exchange=store, ledger=ledger, reservation={"record_name":"ledger-0001.json",
                "sha256":"a" * 64}, repository=Path.cwd(), python_executable=Path(sys.executable),
                timeout_seconds=2, launcher=lambda *a, **k: pytest.fail("launched"))


@pytest.mark.parametrize("elapsed,failure,expected", [
    (0.0, "worker_timeout", ["launch", "resume", "wait", "kill", "wait", "close"]),
    (0.05, "worker_not_resumed", ["launch", "kill", "close"]),
])
def test_deadline_kills_owned_tree_and_never_retries(tmp_path, monkeypatch, elapsed, failure, expected):
    from harness import bulletin_model_worker as worker
    # Control the supervision clock, not disk speed or the production deadline.
    ticks = iter((0.0, elapsed))
    monkeypatch.setattr(worker, "time", SimpleNamespace(monotonic=lambda: next(ticks)))
    req, actions = request(), []
    class Owned:
        def resume(self): actions.append("resume"); return True
        def wait(self, timeout):
            actions.append("wait")
            assert timeout == (.05 if actions.count("wait") == 1 else .5)
            return None
        def signal_tree(self): actions.append("kill"); return True
        def close(self): actions.append("close")
    def launch(argv, **kwargs):
        actions.append("launch")
        assert "-I" in argv and "-S" in argv
        assert not any("PROXY" in key or "TOKEN" in key or key == "PYTHONPATH" for key in kwargs["env"])
        return Owned()
    with PrivateExchange.create(tmp_path / "ledger") as ledger, PrivateExchange.create(tmp_path / "call") as store:
        digest = ledger.put("ledger-0001.json", canonical_bytes(reservation(req)), max_bytes=8192)
        result = supervise_generation(req, exchange=store, ledger=ledger, reservation={"record_name":"ledger-0001.json",
            "sha256":digest}, repository=Path.cwd(), python_executable=Path(sys.executable),
            timeout_seconds=.05, launcher=launch)
        assert result["outcome"] == "unknown" and result["failure"] == failure
        assert actions == expected


@pytest.fixture
def fake_server():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append(("GET", self.path))
            self.answer({"models": [{"name": "fixture", "digest": "a" * 64}]})
        def do_POST(self):
            length = int(self.headers["Content-Length"])
            assert length <= 262144
            calls.append(("POST", json.loads(self.rfile.read(length))))
            self.answer({"model": "fixture", "message": {"content": "fixture only"}, "eval_count": 2})
        def answer(self, value):
            raw = canonical_bytes(value)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows owned-job component")
@pytest.mark.parametrize("stage", ["readiness", "smoke"])
def test_owned_child_strict_transport_uses_ephemeral_fixture_only(tmp_path, fake_server, stage):
    origin, calls = fake_server
    req = request(stage, origin)
    with PrivateExchange.create(tmp_path / "ledger") as ledger, PrivateExchange.create(tmp_path / "call") as store:
        digest = ledger.put("ledger-0001.json", canonical_bytes(reservation(req)), max_bytes=8192)
        result = supervise_generation(req, exchange=store, ledger=ledger,
            reservation={"record_name": "ledger-0001.json", "sha256": digest},
            repository=Path.cwd(), python_executable=Path(sys.executable), timeout_seconds=10)
        assert result["backend_valid"] is True and result["text"] == "fixture only", result
        assert [c[0] for c in calls] == (["GET", "POST"] if stage == "readiness" else ["POST"])
        assert calls[-1][1]["options"]["num_predict"] == req["max_tokens"]
        terminal = json.loads(store.read("transport-002.json", max_bytes=4096))
        assert terminal["event"]["phase"] == "terminal"
        assert terminal["event"]["request_send_started"] is True
        assert terminal["reservation_id"] == req["reservation_id"]
        with pytest.raises(WorkerError):
            supervise_generation(req, exchange=store, ledger=ledger,
                reservation={"record_name": "ledger-0001.json", "sha256": digest},
                repository=Path.cwd(), python_executable=Path(sys.executable), timeout_seconds=10)
        with PrivateExchange.create(tmp_path / "different-call") as second:
            with pytest.raises(WorkerError):
                supervise_generation(req, exchange=second, ledger=ledger,
                    reservation={"record_name": "ledger-0001.json", "sha256": digest},
                    repository=Path.cwd(), python_executable=Path(sys.executable), timeout_seconds=10,
                    launcher=lambda *a, **k: pytest.fail("replayed reservation"))
        assert len(calls) == (2 if stage == "readiness" else 1)


def test_record_failure_before_io_and_replaced_identity_are_not_promoted(tmp_path, monkeypatch):
    req, calls = request("smoke"), []
    with PrivateExchange.create(tmp_path / "call") as store:
        original = store.put
        def fail(name, *args, **kwargs):
            if name.startswith("transport-"):
                raise OSError("synthetic recorder failure")
            return original(name, *args, **kwargs)
        monkeypatch.setattr(store, "put", fail)
        result = run_worker(req, store, reservation(req), transport_factory=fixture_factory(calls))
        assert result["backend_valid"] is False and result["outcome"] == "unknown"
        assert len(calls) == 1  # Fake entered only; event sink failed before any real I/O.
        from harness.private_artifact_fs import ArtifactIdentity
        wrong = ArtifactIdentity(store.identity.platform, store.identity.device, store.identity.inode + 1)
        with pytest.raises(Exception, match="parent_identity_mismatch"):
            PrivateExchange.attach(tmp_path / "call", expected=wrong)


@pytest.mark.parametrize("profile_change", [{"backend": "serve"}, {"selectors": ["fixture", "other"]},
    {"endpoint_url": "http://localhost:9999"}, {"generation_config": {"num_ctx": True}},
    {"token": "never admitted"}, {"expected_ollama_digest": "unknown"}])
def test_profile_rejects_fallback_implicit_context_and_private_fields(tmp_path, profile_change):
    req = request()
    req["profile"].update(profile_change)
    with PrivateExchange.create(tmp_path / "call") as store:
        with pytest.raises(WorkerError):
            run_worker(req, store, reservation(req), transport_factory=lambda *a, **k: pytest.fail("constructed transport"))


def test_forged_pre_io_send_flag_is_not_recorded(tmp_path):
    req = request("smoke")
    def factory(policy, *, observer):
        def send(*args):
            observer({"attempt_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "method": "POST",
                "path": "/api/chat", "phase": "connection_attempt", "connection_started": False,
                "request_send_started": True, "outcome": None, "code": None, "status": None})
            pytest.fail("malformed event accepted")
        return send
    with PrivateExchange.create(tmp_path / "call") as store:
        result = run_worker(req, store, reservation(req), transport_factory=factory)
        assert result["outcome"] == "unknown" and result["backend_valid"] is False
        with pytest.raises(Exception):
            store.read("transport-000.json", max_bytes=4096)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows owned-job component")
@pytest.mark.parametrize("startup_delay", [0, 3.4])
def test_recorder_hang_kills_descendant_before_socket_send(tmp_path, fake_server, startup_delay, text_once_written):
    from harness.cross_harness_process import start_owned_process
    from tests.process_startup_fixtures import ReadyOwnedProcess, windows_pid_is_running
    import time
    origin, calls = fake_server
    req = request("smoke", origin)
    owned = []
    def launch(argv, **kwargs):
        # Trusted scripted instrumentation control; never enabled in production.
        # 60s outlasts 30s readiness + 6s cleanup, excluding a natural-exit pass.
        code = '''import sys,time,subprocess
time.sleep(float(sys.argv[2]))
sys.path.insert(0,sys.argv[1])
from harness.bulletin_model_exchange import PrivateExchange
original=PrivateExchange.put
def blocked(self,name,data,**kwargs):
    if name == 'transport-000.json':
        child=subprocess.Popen([sys.executable,'-I','-S','-c','import time;time.sleep(60)'])
        original(self,'descendant.pid',str(child.pid).encode(),max_bytes=64)
        time.sleep(60)
    return original(self,name,data,**kwargs)
PrivateExchange.put=blocked
from harness.bulletin_model_worker import main
raise SystemExit(main())'''
        process = start_owned_process((str(sys.executable), "-I", "-S", "-c", code, str(Path.cwd()), str(startup_delay)), **kwargs)
        wrapped = ReadyOwnedProcess(process, store.path / "descendant.pid", text_once_written, windows_pid_is_running)
        owned.append(wrapped)
        return wrapped
    with PrivateExchange.create(tmp_path / "ledger") as ledger, PrivateExchange.create(tmp_path / "call") as store:
        digest = ledger.put("ledger-0001.json", canonical_bytes(reservation(req)), max_bytes=8192)
        result = supervise_generation(req, exchange=store, ledger=ledger,
            reservation={"record_name": "ledger-0001.json", "sha256": digest},
            repository=Path.cwd(), python_executable=Path(sys.executable), timeout_seconds=2, launcher=launch)
        # Startup is a separate bounded precondition. The real two-second wait
        # and kill begin only after the descendant is observed alive.
        assert owned[0].ready_at is not None, "descendant readiness was not established"
        assert result["outcome"] == "unknown" and result["failure"] == "worker_timeout"
        assert time.monotonic() - owned[0].ready_at < 6
        assert calls == []
        pid = int(store.read("descendant.pid", max_bytes=64))
        assert pid == owned[0].pid and not windows_pid_is_running(pid)
