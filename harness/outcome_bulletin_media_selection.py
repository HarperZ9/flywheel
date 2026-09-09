"""Normalized run and artifact selection for Bulletin media publishing."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from .evidence_public import exact_request
from .file_backed_store import FileBackedHarnessStore, read_jsonl
from .journey_types import SHA256_PATTERN
from .outcome_bulletin_media_core import (
    MAX_MEDIA_BYTES,
    _ARTIFACT,
    _b64u,
    _fail,
    _one_text,
    _private_text,
    _sniff,
)
from .private_artifact_fs import open_artifact_root, root_identity

RUNS_REQUEST_SCHEMA = "flywheel.bulletin-media-runs-request/v1"
RUNS_RESPONSE_SCHEMA = "flywheel.bulletin-media-runs-response/v1"
ARTIFACTS_REQUEST_SCHEMA = "flywheel.bulletin-media-artifacts-request/v1"
ARTIFACTS_RESPONSE_SCHEMA = "flywheel.bulletin-media-artifacts-response/v1"
_RUN = re.compile(r"run_[A-Za-z0-9._:-]{1,128}\Z")
_CURSOR = re.compile(r"(0|[1-9][0-9]{0,8})\Z")


def list_media_runs(body: dict, *, run_root: Path) -> dict:
    exact_request(body, {"schema", "limit", "cursor"},
                  optional={"limit", "cursor"})
    if body.get("schema") != RUNS_REQUEST_SCHEMA:
        _fail()
    limit, start = _limit(body.get("limit")), _cursor(body.get("cursor"))
    store = _store(run_root)
    page, has_more = _run_page(store.runs_path, start, limit)
    counts = _artifact_counts(store.artifacts_path, {
        _run_id(row.get("run_id")) for row in page})
    window = [_public_run(row, counts) for row in page]
    return {"schema": RUNS_RESPONSE_SCHEMA, "runs": window,
            "next_cursor": str(start + limit) if has_more else None}


def list_media_artifacts(body: dict, *, run_root: Path) -> dict:
    exact_request(body, {"schema", "run_id"})
    if body.get("schema") != ARTIFACTS_REQUEST_SCHEMA:
        _fail()
    run_id, store = _run_id(body.get("run_id")), _store(run_root)
    rows = []
    for row in _artifact_rows(store, run_id):
        try:
            rows.append(_public_artifact(_artifact_detail(store, row, run_id)))
        except Exception:
            pass
    return {"schema": ARTIFACTS_RESPONSE_SCHEMA, "run_id": run_id,
            "artifacts": rows}


def resolve_selected_media(req: dict, *, run_root: Path) -> list[dict[str, str]]:
    run_id, store = _run_id(req.get("run_id")), _store(run_root)
    raw = req.get("media")
    if (type(raw) is not list or not 1 <= len(raw) <= 3 or any(
            type(item) is not dict or set(item) != {"artifact_id", "alt"}
            for item in raw)):
        _fail()
    selected, seen = [], set()
    for item in raw:
        artifact = _artifact_id(item.get("artifact_id"))
        if artifact in seen:
            _fail()
        seen.add(artifact)
        selected.append((artifact, _one_text(item.get("alt"), 800)))
    details = {}
    for row in _artifact_rows(store, run_id):
        if row.get("artifact_id") in seen:
            detail = _artifact_detail(store, row, run_id)
            artifact = detail["artifact_id"]
            if artifact in details:
                _fail()
            details[artifact] = detail
    out = []
    for artifact, alt in selected:
        if artifact not in details:
            _fail()
        out.append({"artifact_id": artifact, "label": details[artifact]["label"],
                    "relative_path": details[artifact]["relative_path"],
                    "alt": alt})
    return out


def _store(run_root: Path) -> FileBackedHarnessStore:
    return FileBackedHarnessStore(Path(run_root))


def _rows(path: Path) -> list[dict]:
    return [row for row in read_jsonl(path) if type(row) is dict]


def _iter_rows(path: Path):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                row = json.loads(line)
                if type(row) is dict:
                    yield row


def _run_page(path: Path, start: int, limit: int) -> tuple[list[dict], bool]:
    page, index = [], 0
    for row in _iter_rows(path):
        _run_id(row.get("run_id"))
        if index < start:
            index += 1
            continue
        if len(page) < limit:
            page.append(row)
            index += 1
            continue
        return page, True
    return page, False


def _artifact_counts(path: Path, run_ids: set[str]) -> Counter:
    counts = Counter()
    if not run_ids:
        return counts
    for artifact in _iter_rows(path):
        run_id = artifact.get("run_id")
        if type(run_id) is str and run_id in run_ids:
            counts[run_id] += 1
    return counts


def _limit(value: object) -> int:
    if value is None:
        return 50
    if type(value) is not int or not 1 <= value <= 100:
        _fail()
    return value


def _cursor(value: object) -> int:
    if value is None:
        return 0
    if type(value) is not str or _CURSOR.fullmatch(value) is None:
        _fail()
    return int(value)


def _run_id(value: object) -> str:
    run = _one_text(value, 160)
    if _RUN.fullmatch(run) is None:
        _fail()
    return run


def _artifact_id(value: object) -> str:
    artifact = _one_text(value, 120)
    if _ARTIFACT.fullmatch(artifact) is None:
        _fail()
    return artifact


def _safe_text(value: object, limit: int) -> str:
    return "" if value in (None, "") else _one_text(value, limit)


def _public_run(row: dict, counts: Counter) -> dict:
    run_id = _run_id(row.get("run_id"))
    return {"run_id": run_id, "kind": _safe_text(row.get("kind"), 80),
            "title": _safe_text(row.get("title"), 160),
            "status": _safe_text(row.get("status"), 80),
            "created_utc": _safe_text(row.get("created_utc"), 80),
            "updated_utc": _safe_text(row.get("updated_utc"), 80),
            "artifact_count": counts[run_id]}


def _artifact_rows(store: FileBackedHarnessStore, run_id: str) -> list[dict]:
    runs = [row for row in _rows(store.runs_path) if row.get("run_id") == run_id]
    if len(runs) != 1:
        _fail()
    return [row for row in _rows(store.artifacts_path)
            if row.get("run_id") == run_id]


def _artifact_detail(store: FileBackedHarnessStore, row: dict, run_id: str) -> dict:
    if row.get("run_id") != run_id:
        _fail()
    sha = row.get("sha256")
    if type(sha) is not str or SHA256_PATTERN.fullmatch(sha) is None:
        _fail()
    artifact = _artifact_id(row.get("artifact_id"))
    if artifact != f"artifact_{sha[:16]}":
        _fail()
    root = store.artifact_dir.resolve()
    try:
        stored = Path(_private_text(row.get("stored_path"), 2048)).resolve()
        rel = stored.relative_to(root).as_posix()
    except Exception as exc:
        raise ValueError("artifact path is invalid") from exc
    identity = root_identity(store.artifact_dir)
    with open_artifact_root(store.artifact_dir, expected=identity,
                            writable=False) as fs:
        raw = fs.read_bytes(rel, max_bytes=MAX_MEDIA_BYTES)
    if hashlib.sha256(raw).hexdigest() != sha:
        _fail()
    media_type, kind = _sniff(raw)
    return {"artifact_id": artifact,
            "label": _safe_text(row.get("label"), 120) or artifact,
            "kind": kind, "media_type": media_type, "bytes": len(raw),
            "sha256": sha, "expected_media_id": _b64u(hashlib.sha256(raw).digest()),
            "created_utc": _safe_text(row.get("created_utc"), 80),
            "relative_path": rel}


def _public_artifact(detail: dict) -> dict:
    return {key: detail[key] for key in (
        "artifact_id", "label", "kind", "media_type", "bytes", "sha256",
        "expected_media_id", "created_utc")}
