from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import forum
from forum.flight_recorder import normalize_trace
from forum.ledger import Ledger
from forum.storage import FileStorage

from analyzer import analyze


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _prepare_directory(path: Path, allowed_existing: set[str]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    unknown = {child.name for child in path.iterdir()} - allowed_existing
    if unknown:
        raise RuntimeError(f"refusing to overwrite unknown files in {path.name}: {sorted(unknown)}")
    for name in allowed_existing:
        target = path / name
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()


def _build_trace(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    precommit = analysis["precommit"]
    macos = analysis["macos"]
    inputs = analysis["provenance"]["inputs"]
    return [
        {
            "actor": "auditor",
            "kind": "audit_request",
            "id": "request",
            "payload": {
                "question": "Which vLLM CI efficiency hypotheses are supported by pinned public evidence?",
                "repository": analysis["repository"],
                "constraint": "measure first; do not estimate savings from elapsed timestamps",
            },
        },
        {
            "actor": "github-evidence",
            "kind": "source_snapshot",
            "id": "precommit-source",
            "parent": "request",
            "payload": {
                "workflow": analysis["provenance"]["workflows"]["precommit"],
                "snapshot_sha256": inputs["precommit-runs.json"],
                "snapshot_url": analysis["provenance"]["snapshot_urls"]["precommit_runs"],
            },
        },
        {
            "actor": "offline-analyzer",
            "kind": "measurement",
            "id": "precommit-measurement",
            "parent": "precommit-source",
            "payload": {
                "sample_size": precommit["sample_size"],
                "completed_records": precommit["completed_records"],
                "conclusions": precommit["conclusions"],
                "run_elapsed_seconds": precommit["run_elapsed_seconds"],
                "billed_runner_time_seconds": None,
            },
        },
        {
            "actor": "github-evidence",
            "kind": "representative_run",
            "id": "cancelled-run-source",
            "parent": "precommit-measurement",
            "payload": precommit["representative_runs"]["cancelled_workflow"],
        },
        {
            "actor": "auditor",
            "kind": "hypothesis",
            "id": "cancellation-hypothesis",
            "parent": "cancelled-run-source",
            "payload": {
                "claim_state": "inference",
                "proposal": (
                    "Measure cancellation request, runner receipt, process exit, and job completion "
                    "timestamps before changing policy."
                ),
                "estimated_savings_seconds": None,
                "falsifier": (
                    "Reject the hypothesis if cancellation is promptly received or retained work is "
                    "required and does not increase constrained runner occupancy."
                ),
            },
        },
        {
            "actor": "github-evidence",
            "kind": "source_snapshot",
            "id": "macos-source",
            "parent": "request",
            "payload": {
                "workflow": analysis["provenance"]["workflows"]["macos"],
                "snapshot_sha256": inputs["macos-runs.json"],
                "snapshot_url": analysis["provenance"]["snapshot_urls"]["macos_runs"],
            },
        },
        {
            "actor": "offline-analyzer",
            "kind": "measurement",
            "id": "macos-measurement",
            "parent": "macos-source",
            "payload": {
                "sample_size": macos["sample_size"],
                "scheduled_records": macos["scheduled_records"],
                "conclusions": macos["conclusions"],
                "run_elapsed_seconds": macos["run_elapsed_seconds"],
                "billed_runner_time_seconds": None,
            },
        },
        {
            "actor": "github-evidence",
            "kind": "representative_run",
            "id": "macos-job-source",
            "parent": "macos-measurement",
            "payload": macos["representative_run"],
        },
        {
            "actor": "auditor",
            "kind": "hypothesis",
            "id": "cadence-hypothesis",
            "parent": "macos-job-source",
            "payload": {
                "claim_state": "inference",
                "proposal": (
                    "Compare daily versus lower-cadence preview coverage while retaining required "
                    "daily macos-15 coverage."
                ),
                "estimated_savings_seconds": None,
                "falsifier": (
                    "Reject a cadence reduction if macos-26 uniquely detects material defects at a "
                    "rate that justifies the current schedule."
                ),
            },
        },
        {
            "actor": "auditor",
            "kind": "limitations",
            "id": "limitations",
            "parent": "request",
            "payload": {
                "claim_state": "verified",
                "items": analysis["limitations"],
                "estimated_savings_seconds": None,
            },
        },
        {
            "actor": "auditor",
            "kind": "evidence_synthesis",
            "id": "synthesis",
            "parent": "limitations",
            "payload": {
                "claim_state": "verified",
                "bind_event_ids": [
                    "precommit-measurement",
                    "cancelled-run-source",
                    "cancellation-hypothesis",
                    "macos-measurement",
                    "macos-job-source",
                    "cadence-hypothesis",
                    "limitations",
                ],
                "binding_contract": "event id, sequence, payload hash, and entry hash",
                "estimated_savings_seconds": None,
            },
        },
        {
            "actor": "auditor",
            "kind": "conclusion",
            "id": "conclusion",
            "parent": "synthesis",
            "payload": {
                "claim_state": "inference",
                "text": (
                    "The evidence supports two measurement experiments, not an efficiency savings "
                    "claim or an unsolicited patch."
                ),
                "estimated_savings_seconds": None,
            },
        },
    ]


def _persist_forum_ledger(
    trace: list[dict[str, Any]], ledger_dir: Path
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    normalized = normalize_trace(trace, "generic")
    seen_ids: set[Any] = set()
    for event in normalized:
        event_id = event.get("id")
        if event_id is None:
            raise ValueError("every receipt event requires an id")
        if event_id in seen_ids:
            raise ValueError(f"duplicate event id: {event_id}")
        parent_id = event.get("parent_id")
        if parent_id is not None and parent_id not in seen_ids:
            raise ValueError(f"unknown or forward parent {parent_id!r} for event {event_id!r}")
        seen_ids.add(event_id)

    ticks = iter(float(i) for i in range(1, len(normalized) + 1))
    ledger = Ledger(FileStorage(str(ledger_dir)), clock=lambda: next(ticks))
    id_to_seq: dict[Any, int] = {}
    id_to_entry: dict[Any, Any] = {}
    materialized_trace: list[dict[str, Any]] = []
    for event in normalized:
        parent_id = event.get("parent_id")
        parent_seq = id_to_seq.get(parent_id) if parent_id is not None else None
        payload = event["payload"]
        if event["kind"] == "evidence_synthesis":
            bind_ids = payload.get("bind_event_ids")
            if not isinstance(bind_ids, list) or not bind_ids:
                raise ValueError("evidence synthesis requires bind_event_ids")
            bindings = []
            for bind_id in bind_ids:
                bound = id_to_entry.get(bind_id)
                if bound is None:
                    raise ValueError(f"unknown or forward synthesis binding: {bind_id!r}")
                bindings.append(
                    {
                        "event_id": bind_id,
                        "seq": bound.seq,
                        "payload_hash": bound.payload_hash,
                        "entry_hash": bound.entry_hash,
                    }
                )
            payload = {
                key: value for key, value in payload.items() if key != "bind_event_ids"
            }
            payload["bindings"] = bindings
        entry = ledger.append(
            actor=event["actor"],
            kind=event["kind"],
            payload=payload,
            causal_parent=parent_seq,
        )
        event_id = event["id"]
        id_to_seq[event_id] = entry.seq
        id_to_entry[event_id] = entry
        materialized_trace.append(
            {
                "actor": event["actor"],
                "kind": event["kind"],
                "id": event_id,
                **({"parent": parent_id} if parent_id is not None else {}),
                "payload": payload,
            }
        )
    ledger.sync()
    if not ledger.verify(deep=True):
        raise RuntimeError("Forum ledger failed in-process deep verification")
    recovered = Ledger(FileStorage(str(ledger_dir)))
    if not recovered.verify(deep=True):
        raise RuntimeError("Forum ledger failed deep verification after restart")
    entries = recovered.replay()
    for entry in entries:
        try:
            recovered.get_payload(entry.payload_hash)
        except KeyError as exc:
            raise RuntimeError(f"Forum ledger payload missing for seq {entry.seq}") from exc
    return {
        "schema": "vllm-ci-forum-ledger-record/1",
        "forum_version": forum.__version__,
        "entries": len(entries),
        "verified_deep": True,
        "verified_deep_after_restart": True,
        "dangling_parents": 0,
        "payloads_complete": True,
        "merkle_root": recovered.checkpoint(),
        "ledger": [
            {
                "seq": entry.seq,
                "actor": entry.actor,
                "kind": entry.kind,
                "causal_parent": entry.causal_parent,
                "payload_hash": entry.payload_hash,
                "entry_hash": entry.entry_hash,
            }
            for entry in entries
        ],
    }, materialized_trace


def generate(data_dir: Path, artifacts_dir: Path, ledger_dir: Path) -> dict[str, Any]:
    data_dir = Path(data_dir)
    upstream_license = data_dir.parent / "UPSTREAM-LICENSE-vLLM.txt"
    if not upstream_license.is_file():
        raise FileNotFoundError(upstream_license)
    artifacts_dir = Path(artifacts_dir)
    ledger_dir = Path(ledger_dir)
    if artifacts_dir.parent.resolve() != ledger_dir.parent.resolve():
        raise ValueError("artifacts and forum-ledger directories must share a parent")
    _prepare_directory(
        artifacts_dir,
        {"analysis.json", "forum-trace.json", "forum-record.json", "manifest.json"},
    )
    _prepare_directory(ledger_dir, {"entries.jsonl", "payloads.jsonl"})

    analysis = analyze(data_dir)
    trace = _build_trace(analysis)
    _write_json(artifacts_dir / "analysis.json", analysis)
    forum_record, materialized_trace = _persist_forum_ledger(trace, ledger_dir)
    _write_json(artifacts_dir / "forum-trace.json", materialized_trace)
    _write_json(artifacts_dir / "forum-record.json", forum_record)

    base = artifacts_dir.parent
    generated = (
        artifacts_dir / "analysis.json",
        artifacts_dir / "forum-record.json",
        artifacts_dir / "forum-trace.json",
        ledger_dir / "entries.jsonl",
        ledger_dir / "payloads.jsonl",
    )
    manifest = {
        "schema": "vllm-ci-receipt-manifest/1",
        "manifest_self_hash": "excluded to avoid a circular digest",
        "source_files": analysis["provenance"]["inputs"],
        "upstream_licenses": {upstream_license.name: _sha256(upstream_license)},
        "files": {
            path.relative_to(base).as_posix(): _sha256(path)
            for path in sorted(generated, key=lambda item: item.as_posix())
        },
        "forum_merkle_root": forum_record["merkle_root"],
    }
    _write_json(artifacts_dir / "manifest.json", manifest)
    return {"analysis": analysis, "forum_record": forum_record, "manifest": manifest}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the offline vLLM CI evidence receipt.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--artifacts", type=Path, default=Path("artifacts"))
    parser.add_argument("--ledger", type=Path, default=Path("forum-ledger"))
    args = parser.parse_args()
    result = generate(args.data, args.artifacts, args.ledger)
    print(
        json.dumps(
            {
                "schema": "vllm-ci-receipt-build/1",
                "forum_merkle_root": result["forum_record"]["merkle_root"],
                "verified_deep_after_restart": result["forum_record"][
                    "verified_deep_after_restart"
                ],
                "manifest_files": len(result["manifest"]["files"]),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
