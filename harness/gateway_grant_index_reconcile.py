"""Explicit bounded reconciliation for gateway grant proposal indexes."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse, json, os

from .gateway_grant_index import read_limited_json, record_filename, replace_full_index
from .gateway_grant_index_recovery import mark_recovery_required
from .gateway_operation import GatewayOperationError
from .journey_lock import ExclusiveJourneyLock
from .operation_grants import GrantError, _parse_time, _secure_owner_only, _utc_text, _validate_owner_ref

SCHEMA = "flywheel.gateway-grant-index-reconcile/v1"


def _result(owner_ref: str, limit: int, entry_limit: int, *, complete: bool,
            reason: str | None, entries_seen: int, records_seen: int,
            records_indexed: int) -> dict:
    return {"schema": SCHEMA, "owner_ref": owner_ref,
            "coverage_scope": "source_scan_bounded",
            "index_coverage_scope": "maintained_index",
            "complete": complete, "recovery_required": reason,
            "entry_limit": entry_limit, "record_limit": limit,
            "entries_seen": entries_seen, "records_seen": records_seen,
            "records_indexed": records_indexed}


def _source_paths(owner_dir: Path, limit: int,
                  entry_limit: int) -> tuple[list[Path], str | None, int, int]:
    paths, entries_seen, records_seen = [], 0, 0
    try:
        with os.scandir(owner_dir) as entries:
            for entry in entries:
                entries_seen += 1
                if entries_seen > entry_limit:
                    return paths, "SCAN_LIMIT_EXCEEDED", entries_seen, records_seen
                if not entry.name.endswith(".json"):
                    continue
                if not entry.is_file(follow_symlinks=False):
                    return paths, "SOURCE_RECORD_INVALID", entries_seen, records_seen
                records_seen += 1
                if records_seen > limit:
                    return paths, "SCAN_LIMIT_EXCEEDED", entries_seen, records_seen
                paths.append(owner_dir / entry.name)
    except OSError:
        return paths, "SOURCE_RECORD_INVALID", entries_seen, records_seen
    return sorted(paths, key=lambda path: path.name), None, entries_seen, records_seen


def _source_record(path: Path, owner_ref: str) -> dict:
    from .gateway_grant_route import _validate_record
    try:
        _secure_owner_only(path, directory=False)
        record = _validate_record(read_limited_json(path), owner_ref)
        if path.name != record_filename(record["proposal_ref"]):
            raise GrantError("PERMISSION_DENIED")
        return record
    except (GatewayOperationError, GrantError, OSError, TypeError, ValueError):
        raise GrantError("PERMISSION_DENIED") from None


def _mark(owner_dir: Path, owner_ref: str, limit: int, entry_limit: int,
          reason: str, now_text: str, entries_seen: int,
          records_seen: int) -> dict:
    mark_recovery_required(owner_dir, reason, now_text)
    return _result(owner_ref, limit, entry_limit, complete=False, reason=reason,
                   entries_seen=entries_seen, records_seen=records_seen,
                   records_indexed=0)


def reconcile_owner_index(state_root: Path, owner_ref: str, *, limit: int,
                          now_text: str) -> dict:
    _validate_owner_ref(owner_ref)
    if type(limit) is not int or type(limit) is bool or not 1 <= limit <= 10_000:
        raise GatewayOperationError("INVALID_REQUEST")
    _parse_time(now_text)
    entry_limit = limit * 4 + 64
    root = Path(state_root) / "gateway-grant-proposals"
    if not root.exists():
        return _result(owner_ref, limit, entry_limit, complete=True, reason=None,
                       entries_seen=0, records_seen=0, records_indexed=0)
    _secure_owner_only(root, directory=True)
    owner_dir = root / owner_ref
    if not owner_dir.exists():
        return _result(owner_ref, limit, entry_limit, complete=True, reason=None,
                       entries_seen=0, records_seen=0, records_indexed=0)
    _secure_owner_only(owner_dir, directory=True)
    with ExclusiveJourneyLock.acquire(owner_dir / ".lock"):
        paths, reason, entries_seen, records_seen = _source_paths(owner_dir, limit,
                                                                 entry_limit)
        if reason:
            return _mark(owner_dir, owner_ref, limit, entry_limit, reason, now_text,
                         entries_seen, records_seen)
        records = []
        for path in paths:
            try:
                records.append(_source_record(path, owner_ref))
            except GrantError:
                return _mark(owner_dir, owner_ref, limit, entry_limit,
                             "SOURCE_RECORD_INVALID", now_text, entries_seen,
                             records_seen)
        try:
            replace_full_index(owner_dir, records, now_text)
        except Exception:
            return _mark(owner_dir, owner_ref, limit, entry_limit,
                         "INDEX_REPLACE_FAILED", now_text, entries_seen,
                         records_seen)
    return _result(owner_ref, limit, entry_limit, complete=True, reason=None,
                   entries_seen=entries_seen, records_seen=records_seen,
                   records_indexed=len(records))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", required=True)
    parser.add_argument("--owner-ref", required=True)
    parser.add_argument("--limit", type=int, required=True)
    parser.add_argument("--now", default=None)
    args = parser.parse_args(argv)
    now = args.now or _utc_text(datetime.now(timezone.utc).replace(microsecond=0))
    result = reconcile_owner_index(Path(args.state_root), args.owner_ref,
                                   limit=args.limit, now_text=now)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
