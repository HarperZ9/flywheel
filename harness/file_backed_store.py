"""Zero-dependency file-backed run/event/receipt store.

This is the local-core persistence layer for the harness. It is intentionally
plain files and JSONL so the system can operate before FastAPI, PostgreSQL,
queues, object storage, or vector databases exist.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def canonical_json(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def json_sha256(obj: dict) -> str:
    return sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    h = sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


@dataclass
class FileBackedHarnessStore:
    """Append-only local store for runs, events, receipts, and artifacts."""

    root: Path

    @property
    def runs_path(self) -> Path:
        return self.root / "runs.jsonl"

    @property
    def events_path(self) -> Path:
        return self.root / "events.jsonl"

    @property
    def receipts_path(self) -> Path:
        return self.root / "receipts.jsonl"

    @property
    def artifacts_path(self) -> Path:
        return self.root / "artifacts.jsonl"

    @property
    def receipt_body_dir(self) -> Path:
        return self.root / "receipt-bodies"

    @property
    def artifact_dir(self) -> Path:
        return self.root / "artifacts"

    def init(self) -> dict:
        self.root.mkdir(parents=True, exist_ok=True)
        self.receipt_body_dir.mkdir(parents=True, exist_ok=True)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        for path in (self.runs_path, self.events_path, self.receipts_path, self.artifacts_path):
            path.touch(exist_ok=True)
        return {
            "schema": "harness.file-store-init/v1",
            "root": str(self.root),
            "runs_path": str(self.runs_path),
            "events_path": str(self.events_path),
            "receipts_path": str(self.receipts_path),
            "artifacts_path": str(self.artifacts_path),
            "receipt_body_dir": str(self.receipt_body_dir),
            "artifact_dir": str(self.artifact_dir),
        }

    def create_run(self, *, kind: str, title: str = "", inputs: dict | None = None) -> dict:
        self.init()
        run = {
            "schema": "harness.run/v1",
            "run_id": f"run_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}_{uuid4().hex[:12]}",
            "kind": kind,
            "title": title,
            "status": "created",
            "created_utc": utc_now(),
            "updated_utc": utc_now(),
            "inputs": inputs or {},
            "store_root": str(self.root),
        }
        self._append_jsonl(self.runs_path, run)
        self.append_event(
            run_id=run["run_id"],
            event_type="run.created",
            payload={"kind": kind, "title": title},
        )
        return run

    def append_event(self, *, run_id: str, event_type: str, payload: dict | None = None) -> dict:
        self.init()
        event = {
            "schema": "harness.event/v1",
            "event_id": f"evt_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}_{uuid4().hex[:12]}",
            "run_id": run_id,
            "event_type": event_type,
            "timestamp_utc": utc_now(),
            "payload": payload or {},
        }
        event["payload_sha256"] = json_sha256(event["payload"])
        self._append_jsonl(self.events_path, event)
        return event

    def put_receipt(
        self,
        *,
        kind: str,
        body: dict,
        run_id: str = "",
        verdict: str = "RECORDED",
    ) -> dict:
        self.init()
        body_payload = {
            "schema": body.get("schema", "harness.receipt-body/v1"),
            "kind": kind,
            "body": body,
        }
        digest = json_sha256(body_payload)
        body_obj = {
            **body_payload,
            "created_utc": utc_now(),
        }
        body_path = self.receipt_body_dir / f"{digest}.json"
        self._write_json_atomic(body_path, body_obj)
        receipt = {
            "schema": "harness.receipt/v1",
            "receipt_id": f"rcpt_{digest[:16]}",
            "run_id": run_id,
            "kind": kind,
            "verdict": verdict,
            "created_utc": utc_now(),
            "payload_sha256": digest,
            "body_path": str(body_path),
            "dependency_posture": "zero-mandatory",
        }
        self._append_jsonl(self.receipts_path, receipt)
        if run_id:
            self.append_event(
                run_id=run_id,
                event_type="receipt.written",
                payload={"receipt_id": receipt["receipt_id"], "kind": kind, "verdict": verdict},
            )
        return receipt

    def copy_artifact(self, source: Path, *, run_id: str = "", label: str = "") -> dict:
        self.init()
        source = source.resolve()
        digest = file_sha256(source)
        target = self.artifact_dir / f"{digest}{source.suffix}"
        if not target.exists():
            shutil.copy2(source, target)
        artifact = {
            "schema": "harness.artifact/v1",
            "artifact_id": f"artifact_{digest[:16]}",
            "run_id": run_id,
            "label": label,
            "source_path": str(source),
            "stored_path": str(target),
            "sha256": digest,
            "created_utc": utc_now(),
        }
        self._append_jsonl(self.artifacts_path, artifact)
        if run_id:
            self.append_event(
                run_id=run_id,
                event_type="artifact.copied",
                payload={"artifact_id": artifact["artifact_id"], "label": label},
            )
        return artifact

    def artifacts_for_run(self, run_id: str) -> list[dict]:
        self.init()
        return [row for row in read_jsonl(self.artifacts_path) if row.get("run_id") == run_id]

    def snapshot(self) -> dict:
        self.init()
        runs = read_jsonl(self.runs_path)
        events = read_jsonl(self.events_path)
        receipts = read_jsonl(self.receipts_path)
        artifacts = read_jsonl(self.artifacts_path)
        return {
            "schema": "harness.file-store-snapshot/v1",
            "root": str(self.root),
            "runs": len(runs),
            "events": len(events),
            "receipts": len(receipts),
            "artifact_rows": len(artifacts),
            "receipt_bodies": len(list(self.receipt_body_dir.glob("*.json"))),
            "artifacts": len(list(self.artifact_dir.iterdir())),
        }

    def _append_jsonl(self, path: Path, obj: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(obj, sort_keys=True, ensure_ascii=True) + "\n")

    def _write_json_atomic(self, path: Path, obj: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(path)
