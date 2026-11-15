"""LangSmith/Langfuse-style run tree -> normalized trace adapter.

Flattens a nested run tree (runs with id / parent_run_id / run_type / start_time /
end_time / extra.metadata, nested via child_runs) into the normalized trace shape.
Agent-action attributes are carried from each run's `attributes` or
`extra.metadata`; nothing about admission / authority / verification is inferred.
Stdlib-only.
"""

from __future__ import annotations

from typing import Any

_RUN_KIND = {
    "tool": "client",
    "llm": "internal",
    "chain": "internal",
    "retriever": "client",
    "embedding": "internal",
    "prompt": "internal",
    "parser": "internal",
}


def _ns(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _run_attributes(run: dict[str, Any]) -> dict[str, Any]:
    attrs = dict(run.get("attributes") or {})
    metadata = (run.get("extra") or {}).get("metadata") or {}
    for key, value in metadata.items():
        attrs.setdefault(key, value)
    if run.get("run_type") == "tool" and "tool.name" not in attrs:
        attrs["tool.name"] = run.get("name", "")
    return attrs


def _run_to_span(run: dict[str, Any]) -> dict[str, Any]:
    parent = run.get("parent_run_id")
    error = run.get("error")
    return {
        "span_id": str(run.get("id", "")),
        "parent_span_id": str(parent) if parent else None,
        "name": run.get("name", ""),
        "kind": _RUN_KIND.get(run.get("run_type", ""), "internal"),
        "start_unix_ns": _ns(run.get("start_time")),
        "end_unix_ns": _ns(run.get("end_time")),
        "status": {
            "code": "error" if error else "ok",
            "message": str(error) if error else "",
        },
        "attributes": _run_attributes(run),
        "events": [],
    }


def _walk(run: dict[str, Any], out: list[dict[str, Any]]) -> None:
    if not isinstance(run, dict):
        return
    out.append(run)
    for child in run.get("child_runs") or []:
        _walk(child, out)


def normalize_run_tree(root: Any, *, service: str | None = None) -> dict[str, Any]:
    """Normalize a run tree (or list of run trees) into the trace shape."""
    roots = root if isinstance(root, list) else [root]
    runs: list[dict[str, Any]] = []
    for r in roots:
        _walk(r, runs)

    first = roots[0] if roots and isinstance(roots[0], dict) else {}
    trace_id = str(first.get("trace_id") or first.get("id") or "")
    resolved_service = service or first.get("name", "")
    return {
        "trace_id": trace_id,
        "service": resolved_service,
        "spans": [_run_to_span(r) for r in runs],
    }
