"""Durable, CAS-guarded filesystem storage for Evidence Journey v2."""
from __future__ import annotations
from dataclasses import dataclass
import os, re
from pathlib import Path
from typing import Callable
from uuid import uuid4
from .evidence_json import canonical_bytes, canonical_sha256, strict_load_json
from .journey_lock import ExclusiveJourneyLock, JourneyLockBusy, fsync_directory
from .journey_projection import reduce_events
from .journey_types import SHA256_PATTERN, build_event, validate_event, validate_journey_ref
GENESIS_HEAD = None
HEAD_SCHEMA, REQUEST_SCHEMA = "flywheel.evidence-journey-head/v2", "flywheel.evidence-journey-request/v2"
_OWNER_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
class JourneyStoreError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)
@dataclass(frozen=True)
class MutationCommand:
    owner_ref: str; journey_ref: str
    expected_event_head: str | None; client_request_id: str
    operation: str; body: dict
@dataclass(frozen=True)
class MutationAck:
    journey_ref: str; event_head_sha256: str; event_sha256: str
    projection_sha256: str; idempotent_replay: bool
class JourneyStore:
    def __init__(self, state_root: Path, *, lock_timeout_s: float = 2.0,
                 fault_injector: Callable[[str], None] | None = None) -> None:
        self.state_root, self.lock_timeout_s = Path(state_root), lock_timeout_s
        self._fault_injector = fault_injector
    def create(self, command: MutationCommand) -> MutationAck:
        self._validate_command(command, creating=True)
        return self._mutate(command, creating=True)
    def append(self, command: MutationCommand) -> MutationAck:
        self._validate_command(command, creating=False)
        return self._mutate(command, creating=False)
    def load(self, owner_ref: str, journey_ref: str) -> dict:
        self._validate_selector(owner_ref, journey_ref)
        try:
            head = self._read_head(self._journey_dir(owner_ref, journey_ref))
            if head is None:
                raise JourneyStoreError("JOURNEY_NOT_FOUND")
            events = self._events_at_head(self._journey_dir(owner_ref, journey_ref), head)
            projection = reduce_events(events)
            if (self._read_json(self._journey_dir(owner_ref, journey_ref) / "projection.json") != projection
                    or canonical_sha256(projection) != head["projection_sha256"]):
                raise JourneyStoreError("STORE_COMMIT_FAILED")
            return projection
        except JourneyStoreError:
            raise
        except (OSError, ValueError, TypeError):
            raise JourneyStoreError("STORE_COMMIT_FAILED") from None
    def list(self, owner_ref: str) -> list[dict]:
        self._validate_owner(owner_ref)
        root = self._owner_dir(owner_ref)
        if not root.exists():
            return []
        try:
            refs = sorted(path.name for path in root.iterdir()
                          if path.is_dir() and path.name.startswith("jrn_") and (path / "head.json").exists())
            return [self.load(owner_ref, ref) for ref in refs]
        except JourneyStoreError:
            raise
        except OSError:
            raise JourneyStoreError("STORE_COMMIT_FAILED") from None
    def lookup_replay(self, command: MutationCommand) -> MutationAck | None:
        """Return only an already authoritative replay for pre-grant service checks."""
        self._validate_selector(command.owner_ref, command.journey_ref)
        journey_dir = self._journey_dir(command.owner_ref, command.journey_ref)
        if not journey_dir.exists():
            return None
        try:
            with ExclusiveJourneyLock.acquire(journey_dir / ".lock", self.lock_timeout_s):
                head = self._read_head(journey_dir)
                events = self._events_at_head(journey_dir, head) if head else []
                return self._replay(command, journey_dir, events)
        except JourneyLockBusy:
            raise JourneyStoreError("STORE_BUSY") from None
        except JourneyStoreError:
            raise
        except (OSError, ValueError, TypeError):
            raise JourneyStoreError("STORE_COMMIT_FAILED") from None
    def _mutate(self, command: MutationCommand, *, creating: bool) -> MutationAck:
        journey_dir = self._journey_dir(command.owner_ref, command.journey_ref)
        try:
            self._prepare_dirs(journey_dir)
            with ExclusiveJourneyLock.acquire(journey_dir / ".lock", self.lock_timeout_s):
                head = self._read_head(journey_dir)
                events = self._events_at_head(journey_dir, head) if head else []
                replay = self._replay(command, journey_dir, events)
                if replay is not None:
                    self._sync_dirs(journey_dir)
                    return replay
                current = head["event_head_sha256"] if head else GENESIS_HEAD
                if current != command.expected_event_head or creating != (head is None):
                    raise JourneyStoreError("HEAD_CONFLICT")
                return self._commit(command, journey_dir, events)
        except JourneyLockBusy:
            raise JourneyStoreError("STORE_BUSY") from None
        except JourneyStoreError:
            raise
        except (OSError, ValueError, TypeError):
            raise JourneyStoreError("STORE_COMMIT_FAILED") from None
    def _commit(self, command: MutationCommand, journey_dir: Path,
                events: list[dict]) -> MutationAck:
        request_sha = self._request_sha(command)
        event = self._build_event(command, events, request_sha)
        projection = reduce_events([*events, event])
        ack = MutationAck(
            command.journey_ref, event["event_sha256"], event["event_sha256"],
            canonical_sha256(projection), False,
        )
        request = self._request_record(command, request_sha, ack, event["sequence"])
        event_path = journey_dir / "events" / f"{event['sequence']:020d}-{ack.event_sha256}.json"
        request_path = journey_dir / "requests" / f"{self._request_key(command)}.json"
        self._write_immutable(event_path, event, "before_event_fsync")
        self._write_immutable(request_path, request)
        self._replace_json(journey_dir / "projection.json", projection,
                           "before_projection_replace")
        head = {
            "schema": HEAD_SCHEMA, "journey_ref": command.journey_ref,
            "sequence": event["sequence"], "event_head_sha256": ack.event_head_sha256,
            "projection_sha256": ack.projection_sha256,
        }
        self._replace_json(journey_dir / "head.json", head, "before_head_replace")
        self._checkpoint("before_directory_fsync")
        self._sync_dirs(journey_dir)
        return ack
    def _replay(self, command: MutationCommand, journey_dir: Path,
                events: list[dict]) -> MutationAck | None:
        path = journey_dir / "requests" / f"{self._request_key(command)}.json"
        if not path.exists():
            return None
        record = self._read_json(path)
        fields = {"schema", "client_request_sha256", "request_sha256", "sequence",
                  "event_head_sha256", "event_sha256", "projection_sha256"}
        if (set(record) != fields or record.get("schema") != REQUEST_SCHEMA
                or record.get("client_request_sha256") != self._request_key(command)):
            raise JourneyStoreError("STORE_COMMIT_FAILED")
        if record.get("request_sha256") != self._request_sha(command):
            raise JourneyStoreError("IDEMPOTENCY_MISMATCH")
        event = next((item for item in events
                      if item["event_sha256"] == record.get("event_sha256")), None)
        if event is None:
            return None
        sequence = record.get("sequence")
        if (type(sequence) is not int or sequence != event["sequence"]
                or record.get("event_head_sha256") != event["event_sha256"]
                or record.get("projection_sha256") != canonical_sha256(
                    reduce_events(events[:sequence + 1]))):
            raise JourneyStoreError("STORE_COMMIT_FAILED")
        return MutationAck(
            command.journey_ref, record["event_head_sha256"], record["event_sha256"],
            record["projection_sha256"], True,
        )
    def _events_at_head(self, journey_dir: Path, head: dict) -> list[dict]:
        candidates = {}
        for path in (journey_dir / "events").glob("*.json"):
            event = validate_event(self._read_json(path))
            candidates[event["event_sha256"]] = event
        chain, digest = [], head["event_head_sha256"]
        while digest is not None:
            event = candidates.get(digest)
            if event is None:
                raise JourneyStoreError("STORE_COMMIT_FAILED")
            chain.append(event)
            digest = event["prior_event_sha256"]
        chain.reverse()
        if len(chain) != head["sequence"] + 1:
            raise JourneyStoreError("STORE_COMMIT_FAILED")
        reduce_events(chain)
        return chain
    def _build_event(self, command: MutationCommand, events: list[dict], request_sha: str) -> dict:
        body = command.body
        if not events:
            payload = {
                "legacy_label": body["legacy_label"], "goal": body["goal"],
                "intake": body["intake"],
            }
        else:
            payload = body["payload"]
        return build_event(
            journey_ref=command.journey_ref, sequence=len(events),
            event_type=command.operation, occurred_at=body["occurred_at"],
            actor_id=command.owner_ref, request_sha256=request_sha, payload=payload,
            prior_event_sha256=events[-1]["event_sha256"] if events else GENESIS_HEAD,
        )
    def _request_record(self, command: MutationCommand, request_sha: str,
                        ack: MutationAck, sequence: int) -> dict:
        return {
            "schema": REQUEST_SCHEMA, "client_request_sha256": self._request_key(command),
            "request_sha256": request_sha, "sequence": sequence,
            "event_head_sha256": ack.event_head_sha256,
            "event_sha256": ack.event_sha256, "projection_sha256": ack.projection_sha256,
        }
    def _validate_command(self, command: MutationCommand, *, creating: bool) -> None:
        if not isinstance(command, MutationCommand):
            raise TypeError("command must be MutationCommand")
        self._validate_selector(command.owner_ref, command.journey_ref)
        if type(command.client_request_id) is not str or not command.client_request_id:
            raise ValueError("client_request_id must be a non-empty string")
        if type(command.operation) is not str or not command.operation:
            raise ValueError("operation must be a non-empty string")
        if type(command.body) is not dict:
            raise ValueError("body must be an object")
        canonical_bytes(command.body)
        expected = {"legacy_label", "goal", "intake", "occurred_at"} if creating else {
            "payload", "occurred_at",
        }
        if set(command.body) != expected:
            raise ValueError("body has invalid mutation fields")
        if creating and (command.expected_event_head is not GENESIS_HEAD
                         or command.operation != "intake"):
            raise JourneyStoreError("HEAD_CONFLICT")
        if not creating and (type(command.expected_event_head) is not str
                             or SHA256_PATTERN.fullmatch(command.expected_event_head) is None
                             or command.operation == "intake"):
            raise JourneyStoreError("HEAD_CONFLICT")
    def _validate_selector(self, owner_ref: str, journey_ref: str) -> None:
        self._validate_owner(owner_ref)
        validate_journey_ref(journey_ref)
    @staticmethod
    def _validate_owner(owner_ref: str) -> None:
        if type(owner_ref) is not str or _OWNER_PATTERN.fullmatch(owner_ref) is None:
            raise ValueError("owner_ref is invalid")
    def _owner_dir(self, owner_ref: str) -> Path:
        return self.state_root / "journeys" / "v2" / "owners" / owner_ref
    def _journey_dir(self, owner_ref: str, journey_ref: str) -> Path:
        return self._owner_dir(owner_ref) / journey_ref
    @staticmethod
    def _prepare_dirs(journey_dir: Path) -> None:
        (journey_dir / "events").mkdir(parents=True, exist_ok=True)
        (journey_dir / "requests").mkdir(parents=True, exist_ok=True)
    @staticmethod
    def _read_json(path: Path) -> dict:
        return strict_load_json(path.read_bytes())
    def _read_head(self, journey_dir: Path) -> dict | None:
        path = journey_dir / "head.json"
        if not path.exists():
            return None
        head = self._read_json(path)
        if (set(head) != {"schema", "journey_ref", "sequence", "event_head_sha256",
                          "projection_sha256"} or head.get("schema") != HEAD_SCHEMA
                or head.get("journey_ref") != journey_dir.name
                or type(head.get("sequence")) is not int or head["sequence"] < 0
                or SHA256_PATTERN.fullmatch(head.get("event_head_sha256", "")) is None
                or SHA256_PATTERN.fullmatch(head.get("projection_sha256", "")) is None):
            raise JourneyStoreError("STORE_COMMIT_FAILED")
        return head
    @staticmethod
    def _request_sha(command: MutationCommand) -> str:
        return canonical_sha256({
            "owner_ref": command.owner_ref, "journey_ref": command.journey_ref,
            "expected_event_head": command.expected_event_head,
            "operation": command.operation, "body": command.body,
        })
    @staticmethod
    def _request_key(command: MutationCommand) -> str:
        return canonical_sha256(command.client_request_id)
    def _write_immutable(self, path: Path, value: dict, checkpoint: str | None = None) -> None:
        data = canonical_bytes(value)
        try:
            stream = path.open("x+b")
        except FileExistsError:
            stream = path.open("r+b")
        with stream:
            existing = stream.read()
            if existing and existing != data:
                raise JourneyStoreError("STORE_COMMIT_FAILED")
            if not existing:
                stream.write(data)
                stream.flush()
            if checkpoint:
                self._checkpoint(checkpoint)
            os.fsync(stream.fileno())
    def _replace_json(self, path: Path, value: dict, checkpoint: str) -> None:
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as stream:
                stream.write(canonical_bytes(value))
                stream.flush()
                os.fsync(stream.fileno())
            self._checkpoint(checkpoint)
            os.replace(temporary, path)
            with path.open("r+b") as stream:
                os.fsync(stream.fileno())
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
    def _sync_dirs(self, journey_dir: Path) -> None:
        for path in (journey_dir / "events", journey_dir / "requests", journey_dir, *journey_dir.parents[:5]):
            fsync_directory(path)
    def _checkpoint(self, point: str) -> None:
        if self._fault_injector is not None:
            try: self._fault_injector(point)
            except Exception: raise JourneyStoreError("STORE_COMMIT_FAILED") from None
