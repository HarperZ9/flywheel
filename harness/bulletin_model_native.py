"""Parent coordinator for the frozen Flutter actor IPC; no grant HTTP client."""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import ipaddress
from pathlib import Path
from queue import Queue, Empty
import re
from threading import Thread, Timer
import time
from urllib.parse import urlsplit
from .bulletin_model_exchange import PrivateExchange
from .bulletin_model_native_process import NativeProcessCapture, close_from_watchdog, record_start_failure
from .cross_harness_process import start_owned_process
from .evidence_json import canonical_bytes, canonical_sha256, strict_load_json
from .gateway_operation import canonicalize_operation
from .private_artifact_fs import open_artifact_root, PrivateArtifactError, NOT_FOUND
class NativeError(RuntimeError):
    """Fixed diagnostic with no model text, credentials or paths."""
class NativeRecordingError(NativeError):
    """Sticky evidence/record-binding failure; no further dispatch is allowed."""
def _check(ok):
    if not ok:
        raise NativeError("native_invalid")
def _id(value):
    return type(value) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value) is not None
def _sha(value):
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None
def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class NativeLaunch:
    dart: Path
    flutter_snapshot: Path
    flutter_packages: Path
    desktop_root: Path
    fixture_config: Path
    fixture_config_sha256: str
    manifest_sha256: str
    run_id: str
    slot_id: str
    room: str
    parent_ids: tuple[str, ...]
    request_id: str
    gateway_origin: str
    bulletin_origin: str
    env: dict[str, str] = field(default_factory=dict, repr=False)
    setup_seconds: float = 120
    active_seconds: float = 240
    review_seconds: float = 120
    request_timeout_ms: int = 15000


class NativeCoordinator:
    def __init__(self, exchange: PrivateExchange, *, launch: NativeLaunch, reviewer,
                 process_factory=start_owned_process, clock=time.monotonic, sleep=time.sleep):
        self.exchange, self.launch, self.reviewer = exchange, launch, reviewer
        self.factory, self.clock, self.sleep = process_factory, clock, sleep
        self.process = self.watchdog = None
        self.failed = self.started = self.used = self.closed = False
        self.bound = self.config = None
        self.ready_at, self.review_elapsed = None, 0.0

    def _fatal(self):
        self.failed = True
        raise NativeRecordingError("native_recording_failed") from None

    def _put(self, name, value, limit):
        try:
            return self.exchange.put(name, canonical_bytes(value), max_bytes=limit)
        except Exception:
            self._fatal()

    def _read(self, name, limit):
        try:
            return self.exchange.read(name, max_bytes=limit)
        except Exception as exc:
            cause = exc
            while cause is not None:
                if isinstance(cause, PrivateArtifactError) and cause.code == NOT_FOUND:
                    return None
                cause = cause.__cause__
            self._fatal()

    def _wait(self, name, limit, deadline):
        while not self.closed and self.clock() < deadline:
            raw = self._read(name, limit)
            if raw is not None:
                return raw
            if self.process.wait(0) is not None:
                raise NativeError("native_driver_exited")
            self.sleep(min(0.005, max(0, deadline - self.clock())))
        raise NativeError("native_timeout")

    def _admit(self):
        v = self.launch
        _check(all(_id(x) for x in (v.run_id, v.slot_id, v.room, v.request_id, *v.parent_ids))
               and 1 <= len(v.parent_ids) <= 2 and len(set(v.parent_ids)) == len(v.parent_ids)
               and _sha(v.fixture_config_sha256) and _sha(v.manifest_sha256))
        for value, maximum in ((v.setup_seconds, 120), (v.active_seconds, 240), (v.review_seconds, 120)):
            _check(type(value) in (float, int) and 0 < value <= maximum)
        _check(type(v.request_timeout_ms) is int and 0 < v.request_timeout_ms <= 15000)
        for path in (v.dart, v.flutter_snapshot, v.flutter_packages, v.fixture_config, v.desktop_root):
            _check(path.is_absolute() and not path.is_symlink() and path.exists())
        _check(v.desktop_root.is_dir() and all(p.is_file() for p in (v.dart, v.flutter_snapshot, v.flutter_packages)))
        for origin in (v.gateway_origin, v.bulletin_origin):
            parsed = urlsplit(origin)
            _check(parsed.scheme == "http" and parsed.port is not None and ipaddress.ip_address(parsed.hostname).is_loopback
                   and not any((parsed.username, parsed.password, parsed.path, parsed.query, parsed.fragment)))
        with open_artifact_root(v.fixture_config.parent, writable=False) as root:
            raw = root.read_bytes(v.fixture_config.name, max_bytes=65536)
        _check(_digest(raw) == v.fixture_config_sha256)
        self.config = strict_load_json(raw, max_bytes=65536, max_depth=16)
        _check(self.config.get("mode") == "actual_worker_loopback" and self.config.get("base_url") == v.gateway_origin
               and self.config.get("bulletin_base_url") == v.bulletin_origin and type(self.config.get("token")) is str
               and bool(self.config["token"]) and _sha(self.config.get("event_head")))
        for name, pattern in (("journey_ref", r"jrn_[a-f0-9]{32}"), ("credential_ref", r"cred_[a-f0-9]{32}")):
            _check(type(self.config.get(name)) is str and re.fullmatch(pattern, self.config[name]) is not None)

    def prestart(self):
        _check(not self.started and not self.failed and not self.closed)
        self.started = True
        try:
            self._admit(); v = self.launch
            allowed = {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH", "PATHEXT", "LOCALAPPDATA", "APPDATA", "USERPROFILE",
                       "PROGRAMFILES", "PROGRAMFILES(X86)"}
            _check(type(v.env) is dict and set(v.env) <= allowed and all(type(x) is str for x in v.env.values()))
            env = {**v.env, "FLUTTER_SUPPRESS_ANALYTICS": "true", "CI": "true",
                   "BULLETIN_ACTOR_FIXTURE_CONFIG": str(v.fixture_config), "BULLETIN_ACTOR_EXCHANGE": str(self.exchange.path),
                   "BULLETIN_ACTOR_RUN_ID": v.run_id, "BULLETIN_ACTOR_SLOT_ID": v.slot_id, "BULLETIN_ACTOR_ROOM": v.room,
                   "BULLETIN_ACTOR_REQUEST_ID": v.request_id, "BULLETIN_ACTOR_PARENT_IDS": canonical_bytes(list(v.parent_ids)).decode()}
            argv = [str(v.dart), "--packages=" + str(v.flutter_packages), str(v.flutter_snapshot), "test", "--no-pub",
                    "test/bulletin_actor_gateway_driver_test.dart"]
            self.process = NativeProcessCapture(self.factory(argv, cwd=v.desktop_root, stdin_bytes=b"", env=env),
                                                self.exchange, self._base(), on_failure=self._fatal)
            self._watch(v.setup_seconds)
            _check(self.process.resume())
            _check(self._wait("ready.txt", 64, self.clock() + v.setup_seconds) == b"BULLETIN_ACTOR_READY\n")
            self.ready_at = self.clock(); self._watch(v.active_seconds + v.review_seconds)
        except NativeRecordingError as error:
            record_start_failure(self, error)
            raise
        except Exception as error:
            record_start_failure(self, error)
            raise NativeError("native_start_incomplete") from None

    def _watch(self, seconds):
        if self.watchdog:
            self.watchdog.cancel()
        self.watchdog = Timer(seconds, lambda: close_from_watchdog(self)); self.watchdog.daemon = True; self.watchdog.start()

    def bind_model_output(self, invocation_id, assistant_text: bytes):
        _check(self.started and not self.closed and self.bound is None and _id(invocation_id) and type(assistant_text) is bytes)
        value = strict_load_json(assistant_text, max_bytes=32768, max_depth=8)
        self.bound = (invocation_id, assistant_text, value)

    def _base(self):
        return {"schema_version": 1, "run_id": self.launch.run_id, "slot_id": self.launch.slot_id}

    def _active_deadline(self):
        return self.ready_at + self.launch.active_seconds + self.review_elapsed

    def remaining_active_seconds(self):
        """Native lifecycle only; the runner owns the later claim-phase clock."""
        if self.ready_at is None or self.closed or self.failed:
            return 0.0
        return max(0.0, self._active_deadline() - self.clock())

    def _review(self, raw, proposal_sha, action):
        try:
            record = strict_load_json(raw, max_bytes=65536, max_depth=20)
            _check(set(record) == {*self._base(), "proposal_sha256", "review"} and all(record[k] == x for k, x in self._base().items())
                   and type(record["schema_version"]) is int and record["proposal_sha256"] == proposal_sha)
            r = record["review"]; unsigned = {k: x for k, x in r.items() if k != "review_sha256"}
            _check(r["schema"] == "flywheel.gateway-grant-review/v1" and canonical_sha256(unsigned) == r["review_sha256"])
            operation = {"name": "bulletin", "tool": "board_write_post", "governance_tier": "T2", "timeout": 20,
                         "args": {k: action[k] for k in ("room", "body", "parent_id")}, "data_refs": [],
                         "credential_refs": [self.config["credential_ref"]]}
            op = canonicalize_operation("lane.call", operation)
            expected = {"action": "lane.call", "operation": operation, "operation_sha256": op.operation_sha256,
                        "arguments_sha256": op.arguments_sha256, "journey_ref": self.config["journey_ref"],
                        "expected_event_head": self.config["event_head"], "client_request_id": self.launch.request_id,
                        "tool": op.tool, "destination": dict(op.destination), "scopes": list(op.scopes),
                        "data_refs": [], "credential_refs": list(op.credential_refs)}
            _check(set(r) == {*expected, "schema", "proposal_ref", "planned_grant_ref", "record_sha256", "review_sha256",
                             "operation_ref", "execution_plan_sha256", "expires_at"} and
                   all(r[k] == x for k, x in expected.items()) and _sha(r["record_sha256"]) and _sha(r["execution_plan_sha256"]))
            _check(re.fullmatch(r"prp_[a-f0-9]{32}", r["proposal_ref"]) and re.fullmatch(r"gnt_[a-f0-9]{32}", r["planned_grant_ref"])
                   and re.fullmatch(r"op_[a-f0-9]{32}", r["operation_ref"]) and r["expires_at"].endswith("Z") and
                   datetime.fromisoformat(r["expires_at"].replace("Z", "+00:00")) > datetime.now(timezone.utc))
            return record
        except Exception:
            self._fatal()

    def _decision(self, record):
        result = Queue(maxsize=1)
        def call():
            try:
                result.put((True, self.reviewer(deepcopy(record))))
            except Exception:
                result.put((False, None))
        began = self.clock()
        Thread(target=call, daemon=True).start()  # No ledger/dispatch access; late result is ignored.
        try:
            ok, decision = result.get(timeout=self.launch.review_seconds)
            _check(ok)
        except Empty:
            raise NativeError("native_review_timeout") from None
        finally:
            self.review_elapsed = self.clock() - began  # Never trust reviewer-reported duration as clock time.
        _check(self.review_elapsed <= self.launch.review_seconds)
        r = record["review"]
        expected = {**self._base(), "proposal_sha256": record["proposal_sha256"], "review_sha256": r["review_sha256"],
                    "operation_sha256": r["operation_sha256"], "proposal_ref": r["proposal_ref"]}
        try:
            _check(type(decision) is dict and set(decision) == {*expected, "reviewer_id", "reviewer_type", "decision", "duration_ms"}
                   and type(decision["schema_version"]) is int and all(decision[k] == x for k, x in expected.items()) and _id(decision["reviewer_id"])
                   and decision["reviewer_type"] in ("human", "assistant_supervisor") and decision["decision"] in ("approve", "reject")
                   and type(decision["duration_ms"]) is int and 0 <= decision["duration_ms"] <= self.launch.review_seconds * 1000)
            return deepcopy(decision)
        except Exception:
            self._fatal()

    def dispatch(self, action, *, reserve):
        _check(not self.failed and not self.closed and not self.used and self.bound is not None)
        self.used = True; reservation = None; proposal_sha = None
        try:
            v = self.launch; invocation, raw, parsed = self.bound
            _check(type(action) is dict and set(action) == {"action", "room", "parent_id", "body"}
                   and all(type(x) is str for x in action.values()) and action == parsed and action["action"] == "write_reply"
                   and action["room"] == v.room and action["parent_id"] in v.parent_ids and len(action["body"].encode()) <= 4000)
            remaining = int((self._active_deadline() - self.clock()) * 1000); _check(remaining > 0)
            proposal_sha = self._put("proposal.json", {**self._base(), "model_invocation_id": invocation,
                "assistant_text_sha256": _digest(raw), "body_utf8_sha256": _digest(action["body"].encode()), "proposal": action}, 8192)
            self._put("descriptor.json", {**self._base(), "manifest_sha256": v.manifest_sha256, "gateway_origin": v.gateway_origin,
                "bulletin_origin": v.bulletin_origin, "fixture_config_sha256": v.fixture_config_sha256, "proposal_sha256": proposal_sha,
                "request_timeout_ms": min(v.request_timeout_ms, remaining), "remaining_active_ms": remaining,
                "review_wait_max_ms": max(1, int(v.review_seconds * 1000))}, 16384)
            record = self._review(self._wait("review.json", 65536, self._active_deadline()), proposal_sha, action)
            decision = self._decision(record); decision_sha = self._put("decision.json", decision, 8192)
            if decision["decision"] == "approve":
                try:
                    reservation = reserve(record["review"]["operation_sha256"])
                    _check(type(reservation) is dict and reservation.get("slot_id") == v.slot_id and _id(reservation.get("reservation_id"))
                           and reservation.get("operation_sha256") == record["review"]["operation_sha256"])
                except Exception:
                    self._fatal()
                _check(not self.closed and self.clock() < self._active_deadline())
                self._put("dispatch-permit.json", {**self._base(), "reservation_id": reservation["reservation_id"],
                    "decision_sha256": decision_sha, "review_sha256": decision["review_sha256"],
                    "operation_sha256": decision["operation_sha256"]}, 8192)
            return self._result(self._wait("result.json", 16384, self._active_deadline()), proposal_sha, reservation, decision)
        except NativeRecordingError:
            raise
        except NativeError:
            if proposal_sha is None:
                raise
            raw_result = self._read("result.json", 16384)
            if raw_result is not None:
                return self._result(raw_result, proposal_sha, reservation, None)
            return {"disposition": "unknown_delivery", "reservation_id": reservation.get("reservation_id") if reservation else None,
                    "request_entered": None, "response_received": None, "post_id": None, "error_code": "native_incomplete"}
        finally:
            self.close()

    def _result(self, raw, proposal_sha, reservation, decision):
        try:
            value = strict_load_json(raw, max_bytes=16384, max_depth=8)
            _check(set(value) == {*self._base(), "proposal_sha256", "reservation_id", "stage", "disposition", "request_entered",
                                  "response_received", "post_id", "error_code"} and all(value[k] == x for k, x in self._base().items())
                   and type(value["schema_version"]) is int and value["proposal_sha256"] == proposal_sha
                   and value["reservation_id"] == (reservation["reservation_id"] if reservation else None)
                   and all(type(value[k]) is bool for k in ("request_entered", "response_received"))
                   and value["error_code"] in (None, "native_driver_incomplete") and _id(value["stage"])
                   and (value["post_id"] is None or _id(value["post_id"])))
            if value["disposition"] == "response_received":
                _check(reservation is not None and value["request_entered"] and value["response_received"] and value["error_code"] is None)
            elif value["disposition"] == "rejected":
                _check(decision and decision["decision"] == "reject" and reservation is None and
                       not value["request_entered"] and not value["response_received"] and value["post_id"] is None and value["error_code"] is None)
            else:
                _check(value["disposition"] == "incomplete" and not value["response_received"] and value["post_id"] is None
                       and value["error_code"] == "native_driver_incomplete" and (not value["request_entered"] or reservation is not None))
                value = {**value, "disposition": "unknown_delivery"}
            return value
        except Exception:
            self._fatal()

    def close(self):
        if self.watchdog:
            self.watchdog.cancel()
        self.closed = True
        if self.process:
            self.process.close()  # Join an in-flight watchdog capture before releasing its store.
