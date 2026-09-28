from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

import desktop.tool.rowan_tts.jobs as jobs_module
from desktop.tool.rowan_tts.engines import FakeWavEngine
from desktop.tool.rowan_tts.http_server import make_server
from desktop.tool.rowan_tts.jobs import RowanTtsState
from desktop.tool.rowan_tts.provenance import (
    REQUIRED_MODEL_FILES,
    sanitize_generation,
    verify_model_dir_identity,
)


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _Server:
    def __init__(self, tmp_path: Path, *, delay_s: float = 0.0, max_queue: int = 1):
        self.token = "test-token"
        self.port = _port()
        self.state = RowanTtsState(
            engine=FakeWavEngine(delay_s=delay_s),
            out_dir=tmp_path,
            token=self.token,
            max_queue=max_queue,
            max_text_chars=120,
        )
        self.server = make_server("127.0.0.1", self.port, self.state)

    def __enter__(self):
        import threading

        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.state.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def post(self, path: str, body: dict[str, Any], *, token: str | None = None):
        return self.post_raw(path, json.dumps(body).encode("utf-8"), token=token)

    def post_raw(self, path: str, data: bytes, *, token: str | None = None):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token if token is not None else self.token}",
            },
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def get(self, path: str, *, token: str | None = None):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            headers={"Authorization": f"Bearer {token if token is not None else self.token}"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))


def test_requires_authentication(tmp_path: Path):
    with _Server(tmp_path) as server:
        with pytest.raises(urllib.error.HTTPError) as caught:
            server.get("/v1/health", token="wrong")
        assert caught.value.code == 401
        body = json.loads(caught.value.read().decode("utf-8"))
        assert body["code"] == "UNAUTHORIZED"


def test_speak_wait_writes_wav_and_manifest(tmp_path: Path):
    with _Server(tmp_path) as server:
        status, body = server.post(
            "/v1/speak",
            {"text": "Hello Rowan.", "wait": True, "seed": 7},
        )
        assert status == 200
        assert body["state"] == "completed"
        audio = Path(body["audio_path"])
        manifest = Path(body["manifest_path"])
        assert audio.exists()
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        assert payload["text"] == "Hello Rowan."
        assert payload["job"]["seed"] == 7
        assert payload["wav"]["nonsilent"] is True
        assert payload["model"]["backend"] == "fake-wav"
        assert payload["model_observed"] is True
        assert payload["model_observation_basis"] == "engine_metadata"
        assert payload["boundary"] == "full-buffer WAV generation; not streaming or real-time speech"


def test_queue_bound_and_queued_cancel(tmp_path: Path):
    with _Server(tmp_path, delay_s=0.35, max_queue=1) as server:
        _, first = server.post("/v1/speak", {"text": "first", "seed": 1})
        _, second = server.post("/v1/speak", {"text": "second", "seed": 2})
        with pytest.raises(urllib.error.HTTPError) as caught:
            server.post("/v1/speak", {"text": "third", "seed": 3})
        assert caught.value.code == 429

        status, cancelled = server.post(f"/v1/jobs/{second['job_id']}/cancel", {})
        assert status == 200
        assert cancelled["state"] == "cancelled"
        _wait_terminal(server, first["job_id"])
        status, second_done = server.get(f"/v1/jobs/{second['job_id']}")
        assert status == 200
        assert second_done["state"] == "cancelled"


def test_stop_cancels_accepted_queued_jobs_with_manifests(tmp_path: Path):
    with _Server(tmp_path, delay_s=0.35, max_queue=1) as server:
        _, first = server.post("/v1/speak", {"text": "running", "seed": 1})
        _wait_state(server, first["job_id"], "running")
        _, queued = server.post("/v1/speak", {"text": "queued", "seed": 2})
        status, body = server.post("/v1/stop", {})
        assert status == 200
        assert body["ok"] is True

        queued_done = server.state.get(queued["job_id"]).public_summary()
        assert queued_done["state"] == "cancelled"
        manifest = Path(queued_done["manifest_path"])
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        assert payload["reason"] == "service_stopping"
        assert payload["text"] == "queued"
        assert payload["model"] is None
        assert payload["model_observed"] is False
        assert payload["model_observation_basis"] == "unobserved_engine_metadata"


def test_pending_speak_after_stop_returns_503_without_orphan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    validation_started = threading.Event()
    release_validation = threading.Event()
    original_reject = jobs_module.reject_source_tokens

    def delayed_reject(field: str, value: str) -> None:
        if field == "text" and value == "delayed":
            validation_started.set()
            assert release_validation.wait(3), "validation was not released"
        original_reject(field, value)

    monkeypatch.setattr(jobs_module, "reject_source_tokens", delayed_reject)
    with _Server(tmp_path) as server:
        outcome: dict[str, Any] = {}

        def submit() -> None:
            try:
                outcome["accepted"] = server.post(
                    "/v1/speak", {"text": "delayed", "seed": 4}
                )
            except urllib.error.HTTPError as exc:
                outcome["error"] = {
                    "status": exc.code,
                    "body": json.loads(exc.read().decode("utf-8")),
                }

        thread = threading.Thread(target=submit)
        thread.start()
        assert validation_started.wait(3), "request did not reach validation"
        status, body = server.post("/v1/stop", {})
        assert status == 200
        assert body["ok"] is True
        release_validation.set()
        thread.join(timeout=3)
        assert not thread.is_alive()
        assert "accepted" not in outcome
        assert outcome["error"]["status"] == 503
        assert outcome["error"]["body"]["code"] == "SERVICE_STOPPING"
        assert [job.public_summary() for job in server.state._jobs.values()] == []


def test_missing_cancel_reports_not_found(tmp_path: Path):
    with _Server(tmp_path) as server:
        with pytest.raises(urllib.error.HTTPError) as caught:
            server.post("/v1/jobs/tts_missing/cancel", {})
        assert caught.value.code == 404
        body = json.loads(caught.value.read().decode("utf-8"))
        assert body["code"] == "JOB_NOT_FOUND"


def test_malformed_wait_and_timeout_are_typed_json_errors(tmp_path: Path):
    with _Server(tmp_path) as server:
        with pytest.raises(urllib.error.HTTPError) as caught_wait:
            server.post("/v1/speak", {"text": "Hello", "wait": "false"})
        assert caught_wait.value.code == 400
        assert json.loads(caught_wait.value.read().decode("utf-8"))["code"] == "BAD_WAIT"

        with pytest.raises(urllib.error.HTTPError) as caught_timeout:
            server.post("/v1/speak", {"text": "Hello", "timeout_s": "10"})
        assert caught_timeout.value.code == 400
        body = json.loads(caught_timeout.value.read().decode("utf-8"))
        assert body["code"] == "BAD_TIMEOUT"


def test_generation_values_are_bounded():
    with pytest.raises(ValueError, match="max_new_tokens"):
        sanitize_generation({"max_new_tokens": 100000000})
    with pytest.raises(ValueError, match="temperature"):
        sanitize_generation({"temperature": -5})
    with pytest.raises(ValueError, match="top_k"):
        sanitize_generation({"top_k": 1.5})


def test_local_model_identity_verifies_revision_metadata(tmp_path: Path):
    model_dir = _minimal_model_dir(tmp_path, revision="abc123")
    identity = verify_model_dir_identity(model_dir, "abc123")

    assert identity["revision"] == "abc123"
    assert identity["config"]["tts_model_type"] == "voice_design"
    assert identity["metadata_files_checked"] == len(REQUIRED_MODEL_FILES)

    (model_dir / ".cache" / "huggingface" / "download" / "config.json.metadata").write_text(
        "different\n", encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="metadata revision mismatch"):
        verify_model_dir_identity(model_dir, "abc123")


def test_stop_refuses_new_work(tmp_path: Path):
    with _Server(tmp_path) as server:
        status, body = server.post("/v1/stop", {})
        assert status == 200
        assert body["ok"] is True
        with pytest.raises(Exception):
            server.post("/v1/speak", {"text": "after stop"})


def _minimal_model_dir(tmp_path: Path, *, revision: str) -> Path:
    model_dir = tmp_path / "model"
    metadata_root = model_dir / ".cache" / "huggingface" / "download"
    config = {
        "model_type": "qwen3_tts",
        "tokenizer_type": "qwen3_tts_tokenizer_12hz",
        "tts_model_size": "1b7",
        "tts_model_type": "voice_design",
    }
    for name in REQUIRED_MODEL_FILES:
        path = model_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if name == "config.json":
            path.write_text(json.dumps(config), encoding="utf-8")
        elif name == "README.md":
            path.write_text("---\nlicense: apache-2.0\n---\n", encoding="utf-8")
        else:
            path.write_bytes(b"placeholder")
        meta = metadata_root / f"{name}.metadata"
        meta.parent.mkdir(parents=True, exist_ok=True)
        meta.write_text(f"{revision}\n", encoding="utf-8")
    return model_dir


def _wait_terminal(server: _Server, job_id: str):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        _, body = server.get(f"/v1/jobs/{job_id}")
        if body["state"] in {"completed", "cancelled", "failed"}:
            return body
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def _wait_state(server: _Server, job_id: str, state: str):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        _, body = server.get(f"/v1/jobs/{job_id}")
        if body["state"] == state:
            return body
        time.sleep(0.05)
    raise AssertionError(f"job did not reach {state}")
