"""Fixture helpers for live-screen gateway HTTP integration tests."""

from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

from harness import gateway
from harness.gateway_auth import DEFAULT_HOSTS
from harness.journey_store import JourneyStore, MutationCommand
from harness.live_screen_feed import LiveScreenManager, SourceDescriptor
from harness.live_screen_scheduler import LiveScreenProducerScheduler
from harness.live_screen_types import SyntheticCaptureSource
from tests.http_fixture_client import request as http_request

NOW = "2026-09-15T12:00:00Z"
TOKEN = "synthetic-live-screen-http-token"
OWNER = "owner_" + "a" * 32
OTHER_OWNER = "owner_" + "b" * 32
JOURNEY = "jrn_" + "a" * 32
SOURCE = "display:primary"
BODY_SESSION = "body-session-http"
INSTRUMENT = "screen-http"
READY_TIMEOUT_S = 5.0


def json_bytes(data: dict) -> bytes:
    return json.dumps(data, separators=(",", ":")).encode("utf-8")


def operation(control: str, **extra) -> dict:
    value = {"control": control, "data_refs": [], "credential_refs": []}
    value.update(extra)
    return value


def open_operation(*, start_immediately: bool = True) -> dict:
    return operation(
        "open",
        body_session_ref=BODY_SESSION,
        instrument_ref=INSTRUMENT,
        sources=[{"source_id": SOURCE}],
        destination="openai_responses:vision",
        model="gpt-6-astra",
        delivery_mode="sampled_image",
        expires_after_ms=30_000,
        buffer_frames_per_source=3,
        max_frame_bytes=128,
        start_immediately=start_immediately,
    )


def live_manager() -> LiveScreenManager:
    manager = LiveScreenManager(utc_clock=lambda: NOW)
    manager.register_source(
        SourceDescriptor(
            SOURCE,
            "display",
            "Synthetic primary display",
            bounds=(0, 0, 16, 16),
            backend="synthetic",
        ),
        lambda: SyntheticCaptureSource(
            SOURCE,
            [b"frame-a", b"frame-b", b"frame-c"],
            width=16,
            height=16,
        ),
    )
    return manager


def create_journey(home: Path, owner_ref: str = OWNER) -> str:
    ack = JourneyStore(home / "state").create(
        MutationCommand(
            owner_ref,
            JOURNEY,
            None,
            "create-live-screen-http",
            "intake",
            {
                "legacy_label": None,
                "goal": "live-screen HTTP custody",
                "intake": {},
                "occurred_at": NOW,
            },
        )
    )
    return ack.event_head_sha256


class DeterministicScheduler(LiveScreenProducerScheduler):
    def _ensure_loop(self) -> None:
        pass


class _ReadyHTTPServer(ThreadingHTTPServer):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.started = threading.Event()
        self.ready = threading.Event()

    def serve_forever(self, poll_interval: float = 0.5) -> None:
        self.started.set()
        super().serve_forever(poll_interval)

    def service_actions(self) -> None:
        self.ready.set()
        super().service_actions()


class LiveGateway:
    def __init__(
        self,
        home: Path,
        *,
        owner_ref: str,
        manager: LiveScreenManager,
        scheduler: LiveScreenProducerScheduler,
    ) -> None:
        self.home = home
        self.home.mkdir(parents=True, exist_ok=True)
        (self.home / "owner.ref").write_text(owner_ref, encoding="ascii")
        gateway_run_root = self.home / "run"
        gateway_run_root.mkdir()
        repo_root = Path(__file__).resolve().parents[1]

        class Handler(gateway._Handler):
            auth_token = TOKEN
            allowed_hosts = DEFAULT_HOSTS
            flywheel_home = home
            root = repo_root
            run_root = str(gateway_run_root)
            clock = staticmethod(lambda: NOW)
            live_screen_manager = manager
            live_screen_scheduler = scheduler
            _live_screen_state_root = home / "state"
            operation_service = None
            operation_process_factory = None

            def log_message(self, *_args) -> None:
                pass

        self.handler = Handler
        self.http = _ReadyHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(
            target=self.http.serve_forever,
            kwargs={"poll_interval": 0.01},
            daemon=True,
        )
        self.thread.start()
        if not self.http.ready.wait(READY_TIMEOUT_S):
            self.close()
            raise TimeoutError("live gateway fixture did not start serving")

    @property
    def port(self) -> int:
        return self.http.server_address[1]

    def request(
        self,
        path: str,
        body: dict | None = None,
        *,
        token: str | None = TOKEN,
        host: str | None = None,
    ) -> tuple[int, dict]:
        headers = {}
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        if body is not None:
            headers["Content-Type"] = "application/json"
        if host is not None:
            headers["Host"] = host
        raw = json_bytes(body) if body is not None else None
        status, text = http_request(self.port, path, data=raw, headers=headers)
        return status, json.loads(text)

    def close(self) -> None:
        if self.http.started.is_set():
            self.http.shutdown()
        self.http.server_close()
        self.thread.join(5)


def approve_final(server: LiveGateway, operation_body: dict, request_id: str) -> dict:
    head = JourneyStore(server.home / "state").load(OWNER, JOURNEY)[
        "event_head_sha256"
    ]
    prepare = {
        "schema": "flywheel.gateway-operation/v1",
        "journey_ref": JOURNEY,
        "expected_event_head": head,
        "client_request_id": request_id,
        "operation": operation_body,
    }
    status, proposal = server.request(
        "/api/gateway-grants/prepare/live_screen.control",
        prepare,
    )
    assert status == 200, proposal

    status, approval = server.request(
        "/api/gateway-grants/approve-once",
        {"proposal_ref": proposal["proposal_ref"]},
    )
    assert status == 200, approval

    final = {key: value for key, value in prepare.items() if key != "operation"}
    final.update(operation_body)
    final["grant_ref"] = approval["grant_ref"]
    return final
