"""Query the zero-dependency file-backed harness store."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.file_backed_store import FileBackedHarnessStore, read_jsonl  # noqa: E402


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _matches_run(row: dict[str, Any], run_id: str) -> bool:
    return not run_id or row.get("run_id") == run_id


def query_store(store_root: str, *, run_id: str = "", limit: int = 50) -> dict[str, Any]:
    store = FileBackedHarnessStore(Path(store_root))
    store.init()
    runs = read_jsonl(store.runs_path)
    events = read_jsonl(store.events_path)
    receipts = read_jsonl(store.receipts_path)
    artifacts = read_jsonl(store.artifacts_path)
    selected_runs = [row for row in runs if not run_id or row.get("run_id") == run_id]
    selected_events = [row for row in events if _matches_run(row, run_id)]
    selected_receipts = [row for row in receipts if _matches_run(row, run_id)]
    selected_artifacts = [row for row in artifacts if _matches_run(row, run_id)]
    return {
        "schema": "harness.file-store-query/v1",
        "timestamp_utc": _now(),
        "store_root": str(Path(store_root)),
        "run_id": run_id,
        "summary": {
            "runs": len(selected_runs),
            "events": len(selected_events),
            "receipts": len(selected_receipts),
            "artifacts": len(selected_artifacts),
            "total_runs": len(runs),
            "total_events": len(events),
            "total_receipts": len(receipts),
            "total_artifacts": len(artifacts),
        },
        "runs": selected_runs[-limit:],
        "events": selected_events[-limit:],
        "receipts": selected_receipts[-limit:],
        "artifacts": selected_artifacts[-limit:],
    }


def render_markdown(result: dict[str, Any]) -> str:
    summary = result["summary"]
    lines = [
        "# Harness file-store query",
        "",
        f"- Schema: `{result['schema']}`",
        f"- Store root: `{result['store_root']}`",
        f"- Run id: `{result['run_id'] or 'all'}`",
        f"- Runs: `{summary['runs']}`",
        f"- Events: `{summary['events']}`",
        f"- Receipts: `{summary['receipts']}`",
        f"- Artifacts: `{summary['artifacts']}`",
        "",
        "## Runs",
        "",
        "| Run id | Kind | Status | Created UTC |",
        "|---|---|---|---|",
    ]
    for row in result["runs"]:
        lines.append(
            "| {run_id} | {kind} | {status} | {created} |".format(
                run_id=row.get("run_id", ""),
                kind=row.get("kind", ""),
                status=row.get("status", ""),
                created=row.get("created_utc", ""),
            )
        )
    lines.extend(["", "## Receipts", "", "| Receipt id | Kind | Verdict | Payload SHA-256 |", "|---|---|---|---|"])
    for row in result["receipts"]:
        lines.append(
            "| {receipt_id} | {kind} | {verdict} | {sha} |".format(
                receipt_id=row.get("receipt_id", ""),
                kind=row.get("kind", ""),
                verdict=row.get("verdict", ""),
                sha=row.get("payload_sha256", ""),
            )
        )
    lines.extend(["", "## Artifacts", "", "| Artifact id | Label | Stored path | SHA-256 |", "|---|---|---|---|"])
    for row in result["artifacts"]:
        lines.append(
            "| {artifact_id} | {label} | {stored_path} | {sha} |".format(
                artifact_id=row.get("artifact_id", ""),
                label=row.get("label", ""),
                stored_path=row.get("stored_path", ""),
                sha=row.get("sha256", ""),
            )
        )
    return "\n".join(lines) + "\n"


def _write(path_text: str, text: str) -> None:
    if not path_text:
        return
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store-root", default="C:/tmp/harness_file_store")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--out", default="")
    parser.add_argument("--markdown-out", default="")
    args = parser.parse_args(argv)

    result = query_store(args.store_root, run_id=args.run_id, limit=args.limit)
    text = json.dumps(result, indent=2, sort_keys=True)
    print(text)
    _write(args.out, text)
    if args.markdown_out:
        _write(args.markdown_out, render_markdown(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
