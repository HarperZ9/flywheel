"""Inventory scratch, temp, session, and benchmark artifact context surfaces.

This command records metadata only: paths, sizes, mtimes, suffixes, and coarse
classification. It does not read file bodies, print secrets, or copy scanned
source files into the store.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.file_backed_store import FileBackedHarnessStore  # noqa: E402


SKIP_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "receipt-bodies",
}

SECRET_HINTS = (
    ".env",
    "secret",
    "token",
    "credential",
    "key",
    "password",
    "cookie",
)

BENCH_HINTS = (
    "m7",
    "benchmark",
    "scorecard",
    "provider_matrix",
    "stateful",
    "eval",
    "outcome",
)

SESSION_HINTS = (
    "codex",
    "claude",
    "opencode",
    "session",
    "thread",
    "conversation",
)

SCRATCH_HINTS = (
    ".scratch",
    "scratch",
    "tmp",
    "temp",
    "midflight",
    "mid-flight",
)


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _split_roots(raw: str) -> list[Path]:
    return [Path(item.strip()) for item in raw.split(";") if item.strip()]


def _mtime(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat().replace("+00:00", "Z")
    except OSError:
        return ""


def _size(path: Path) -> int:
    try:
        return path.stat().st_size if path.is_file() else 0
    except OSError:
        return 0


def _has_secret_hint(value: str) -> bool:
    lowered = value.lower()
    return any(hint in lowered for hint in SECRET_HINTS)


def classify_path(path: Path) -> list[str]:
    text = str(path).lower()
    labels = []
    if any(hint in text for hint in BENCH_HINTS):
        labels.append("benchmark_artifact")
    if any(hint in text for hint in SESSION_HINTS):
        labels.append("session_context")
    if any(hint in text for hint in SCRATCH_HINTS):
        labels.append("scratch_temp")
    if _has_secret_hint(path.name):
        labels.append("sensitive_name")
    return labels or ["unclassified"]


def _iter_limited(root: Path, *, max_depth: int, max_entries: int):
    yielded = 0
    stack = [(root, 0)]
    while stack and yielded < max_entries:
        current, depth = stack.pop()
        try:
            children = sorted(current.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            continue
        for child in children:
            if yielded >= max_entries:
                break
            if child.is_dir() and child.name in SKIP_NAMES:
                continue
            yielded += 1
            yield child, depth + 1
            if child.is_dir() and depth + 1 < max_depth:
                stack.append((child, depth + 1))


def inventory_root(root: Path, *, max_depth: int, max_entries: int) -> dict[str, Any]:
    root = root.expanduser()
    exists = root.exists()
    rows: list[dict[str, Any]] = []
    if exists:
        for path, depth in _iter_limited(root, max_depth=max_depth, max_entries=max_entries):
            labels = classify_path(path)
            rows.append({
                "path": str(path),
                "name": path.name,
                "kind": "directory" if path.is_dir() else "file",
                "suffix": path.suffix.lower() if path.is_file() else "",
                "depth": depth,
                "size_bytes": _size(path),
                "mtime_utc": _mtime(path),
                "labels": labels,
                "sensitive_name": "sensitive_name" in labels,
                "content_read": False,
            })
    return {
        "root": str(root),
        "exists": exists,
        "max_depth": max_depth,
        "max_entries": max_entries,
        "observed_entries": len(rows),
        "truncated": len(rows) >= max_entries,
        "entries": rows,
    }


def build_inventory(args) -> dict[str, Any]:
    roots = _split_roots(args.roots)
    root_rows = [
        inventory_root(root, max_depth=args.max_depth, max_entries=args.max_entries_per_root)
        for root in roots
    ]
    entries = [entry for row in root_rows for entry in row["entries"]]
    label_counts: dict[str, int] = {}
    for entry in entries:
        for label in entry["labels"]:
            label_counts[label] = label_counts.get(label, 0) + 1
    return {
        "schema": "harness.context-inventory/v1",
        "timestamp_utc": _now(),
        "secret_policy": "metadata-only; file bodies are not read; sensitive names are flagged, not opened",
        "roots_requested": [str(root) for root in roots],
        "roots": root_rows,
        "summary": {
            "roots": len(root_rows),
            "existing_roots": sum(1 for row in root_rows if row["exists"]),
            "entries": len(entries),
            "files": sum(1 for entry in entries if entry["kind"] == "file"),
            "directories": sum(1 for entry in entries if entry["kind"] == "directory"),
            "sensitive_name_entries": sum(1 for entry in entries if entry["sensitive_name"]),
            "label_counts": label_counts,
        },
    }


def render_markdown(obj: dict[str, Any]) -> str:
    summary = obj["summary"]
    lines = [
        "# Context inventory",
        "",
        f"- Schema: `{obj['schema']}`",
        f"- Timestamp UTC: `{obj['timestamp_utc']}`",
        f"- Secret policy: {obj['secret_policy']}",
        f"- Existing roots: `{summary['existing_roots']}` / `{summary['roots']}`",
        f"- Entries: `{summary['entries']}`",
        f"- Sensitive-name entries: `{summary['sensitive_name_entries']}`",
        "",
        "## Label counts",
        "",
    ]
    for label, count in sorted(summary["label_counts"].items()):
        lines.append(f"- `{label}`: `{count}`")
    lines.extend(["", "## Roots", "", "| Root | Exists | Entries | Truncated |", "|---|---:|---:|---:|"])
    for row in obj["roots"]:
        lines.append(
            "| {root} | {exists} | {entries} | {truncated} |".format(
                root=row["root"].replace("|", "\\|"),
                exists=str(row["exists"]).lower(),
                entries=row["observed_entries"],
                truncated=str(row["truncated"]).lower(),
            )
        )
    return "\n".join(lines) + "\n"


def _write(path_text: str, text: str) -> str:
    if not path_text:
        return ""
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def _store_outputs(obj: dict[str, Any], *, store_root: str, run_id: str, artifacts: list[tuple[str, str]]) -> list[dict[str, Any]]:
    if not store_root:
        return []
    store = FileBackedHarnessStore(Path(store_root))
    outputs = [
        store.put_receipt(
            kind="context_inventory",
            body=obj,
            run_id=run_id,
            verdict="INVENTORIED",
        )
    ]
    for path_text, label in artifacts:
        if path_text and Path(path_text).exists():
            outputs.append(store.copy_artifact(Path(path_text), run_id=run_id, label=label))
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--roots",
        default=(
            "C:/dev/local-model/.scratch;"
            "C:/dev/local-model/scratch;"
            "C:/dev/local-model/artifacts;"
            "C:/tmp;"
            "C:/Users/Zain/.codex;"
            "C:/Users/Zain/.claude;"
            "C:/Users/Zain/AppData/Roaming/opencode;"
            "C:/Users/Zain/AppData/Local/Programs/@opencode-aidesktop"
        ),
        help="semicolon-separated roots to inventory",
    )
    parser.add_argument("--max-depth", type=int, default=3)
    parser.add_argument("--max-entries-per-root", type=int, default=500)
    parser.add_argument("--out", default="")
    parser.add_argument("--markdown-out", default="")
    parser.add_argument("--store-root", default="")
    parser.add_argument("--run-id", default="")
    args = parser.parse_args(argv)

    obj = build_inventory(args)
    json_text = json.dumps(obj, indent=2, sort_keys=True)
    md_text = render_markdown(obj)
    json_path = _write(args.out, json_text)
    md_path = _write(args.markdown_out, md_text)
    store_outputs = _store_outputs(
        obj,
        store_root=args.store_root,
        run_id=args.run_id,
        artifacts=[
            (json_path, "context-inventory-json"),
            (md_path, "context-inventory-markdown"),
        ],
    )
    if store_outputs:
        obj = {**obj, "store_outputs": store_outputs}
        json_text = json.dumps(obj, indent=2, sort_keys=True)
    print(json_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
