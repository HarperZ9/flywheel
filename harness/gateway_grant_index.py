"""Bounded owner-scoped listing index for gateway grant proposals."""
from __future__ import annotations
from datetime import timedelta
from pathlib import Path
import os, sqlite3
from uuid import uuid4
from .evidence_json import canonical_sha256, strict_load_json
from .gateway_grant_index_recovery import clear_recovery_required, recovery_required
from .gateway_operation import GatewayOperationError, PROPOSAL_REF_PATTERN
from .operation_grants import GrantError, _parse_time, _secure_owner_only, _utc_text

INDEX_FILENAME = "proposal-index.sqlite3"
MAX_RECORD_BYTES = 1_048_576
DECIDED_RECENT_SECONDS = 24 * 60 * 60
_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS proposal_index(
  proposal_ref TEXT PRIMARY KEY, record_sha256 TEXT NOT NULL,
  proposal_state TEXT NOT NULL, expires_at TEXT NOT NULL,
  indexed_at TEXT NOT NULL, decided_at TEXT, record_file TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pending_mutation(
  proposal_ref TEXT PRIMARY KEY, record_file TEXT NOT NULL,
  started_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS proposal_index_pending
  ON proposal_index(proposal_state, expires_at, proposal_ref);
CREATE INDEX IF NOT EXISTS proposal_index_decided
  ON proposal_index(decided_at DESC, proposal_ref);
"""


def record_filename(proposal_ref: str) -> str:
    if type(proposal_ref) is not str or PROPOSAL_REF_PATTERN.fullmatch(proposal_ref) is None:
        raise GatewayOperationError("INVALID_REQUEST")
    return f"{canonical_sha256(proposal_ref)}.json"


def read_limited_json(path: Path):
    try:
        with path.open("rb") as stream:
            data = stream.read(MAX_RECORD_BYTES + 1)
    except OSError:
        raise GrantError("PERMISSION_DENIED") from None
    if len(data) > MAX_RECORD_BYTES:
        raise GrantError("PERMISSION_DENIED")
    return strict_load_json(data)


def _index_path(owner_dir: Path) -> Path:
    return Path(owner_dir) / INDEX_FILENAME


def _connect(owner_dir: Path) -> sqlite3.Connection:
    path = _index_path(owner_dir)
    try:
        conn = sqlite3.connect(path)
        conn.executescript(_SCHEMA)
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.commit()
        _secure_owner_only(path, directory=False)
        return conn
    except (OSError, sqlite3.Error) as exc:
        raise ValueError("proposal index unavailable") from exc


def _proposal_json_names(owner_dir: Path, stop_after: int = 2) -> list[str]:
    names, inspected = [], 0
    try:
        with os.scandir(owner_dir) as entries:
            for entry in entries:
                inspected += 1
                if entry.is_file() and entry.name.endswith(".json"):
                    names.append(entry.name)
                if len(names) >= stop_after or inspected >= 64:
                    break
    except OSError as exc:
        raise ValueError("proposal index unavailable") from exc
    if inspected >= 64 and not names:
        names.append("__unknown__")
    return names


def _init_complete(conn: sqlite3.Connection, owner_dir: Path, proposal_ref: str) -> None:
    if conn.execute("SELECT value FROM meta WHERE key='index_complete'").fetchone():
        return
    record_name = record_filename(proposal_ref)
    complete = all(name == record_name for name in _proposal_json_names(owner_dir))
    conn.execute("INSERT INTO meta(key,value) VALUES('index_complete',?)",
                 ("true" if complete else "false",))


def _upsert_row(conn: sqlite3.Connection, record: dict, now_text: str) -> None:
    proposal_ref = record["proposal_ref"]
    state = record["state"]
    if state not in {"prepared", "approved", "rejected"}:
        raise ValueError("proposal state is invalid")
    decided = now_text if state in {"approved", "rejected"} else None
    conn.execute("""
        INSERT INTO proposal_index(proposal_ref,record_sha256,proposal_state,
          expires_at,indexed_at,decided_at,record_file) VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(proposal_ref) DO UPDATE SET
          record_sha256=excluded.record_sha256,
          proposal_state=excluded.proposal_state,
          expires_at=excluded.expires_at,
          indexed_at=excluded.indexed_at,
          record_file=excluded.record_file,
          decided_at=CASE
            WHEN excluded.proposal_state IN ('approved','rejected')
            THEN COALESCE(proposal_index.decided_at, excluded.decided_at)
            ELSE NULL END
        """, (proposal_ref, record["record_sha256"], state,
              record["expires_at"], now_text, decided, record_filename(proposal_ref)))


def _begin_mutation(owner_dir: Path, proposal_ref: str, now_text: str) -> None:
    conn = _connect(owner_dir)
    try:
        _init_complete(conn, owner_dir, proposal_ref)
        conn.execute("""
        INSERT INTO pending_mutation(proposal_ref,record_file,started_at)
        VALUES(?,?,?) ON CONFLICT(proposal_ref) DO UPDATE SET
          record_file=excluded.record_file, started_at=excluded.started_at
        """, (proposal_ref, record_filename(proposal_ref), now_text))
        conn.commit()
    finally:
        conn.close()
    _secure_owner_only(_index_path(owner_dir), directory=False)


def _finish_mutation(owner_dir: Path, record: dict, now_text: str) -> None:
    conn = _connect(owner_dir)
    try:
        _init_complete(conn, owner_dir, record["proposal_ref"])
        _upsert_row(conn, record, now_text)
        conn.execute("DELETE FROM pending_mutation WHERE proposal_ref=?",
                     (record["proposal_ref"],))
        conn.commit()
    finally:
        conn.close()
    _secure_owner_only(_index_path(owner_dir), directory=False)


def replace_indexed_proposal(owner_dir: Path, record: dict, now_text: str,
                             replace_record, path: Path) -> None:
    _begin_mutation(owner_dir, record["proposal_ref"], now_text)
    replace_record(path, record)
    _finish_mutation(owner_dir, record, now_text)


def replace_full_index(owner_dir: Path, records: list[dict], now_text: str) -> None:
    target = _index_path(owner_dir)
    temporary = target.with_name(f".{INDEX_FILENAME}.{uuid4().hex}.tmp")
    conn = sqlite3.connect(temporary)
    try:
        conn.executescript(_SCHEMA)
        conn.execute("INSERT INTO meta(key,value) VALUES('index_complete','true')")
        for record in records:
            _upsert_row(conn, record, now_text)
        conn.commit(); conn.close()
        _secure_owner_only(temporary, directory=False)
        os.replace(temporary, target); _secure_owner_only(target, directory=False)
        clear_recovery_required(owner_dir)
    except Exception:
        conn.close()
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def _parse_cursor(cursor: object, decided: bool) -> tuple[str, str] | None:
    if cursor is None:
        return None
    if type(cursor) is not str:
        raise GatewayOperationError("INVALID_REQUEST")
    parts = cursor.split("|")
    if len(parts) != 4 or parts[0] != "v1" or parts[1] != ("d" if decided else "e"):
        raise GatewayOperationError("INVALID_REQUEST")
    try:
        _parse_time(parts[2])
    except ValueError:
        raise GatewayOperationError("INVALID_REQUEST") from None
    if PROPOSAL_REF_PATTERN.fullmatch(parts[3]) is None:
        raise GatewayOperationError("INVALID_REQUEST")
    return parts[2], parts[3]


def _cursor(row: dict, decided: bool) -> str:
    return f"v1|{'d' if decided else 'e'}|{row['decided_at' if decided else 'expires_at']}|{row['proposal_ref']}"


def _meta_complete(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT value FROM meta WHERE key='index_complete'").fetchone()
    return bool(row and row[0] == "true")


def _pending_mutations(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM pending_mutation").fetchone()[0])


def _status(complete: bool, pending: int = 0) -> str:
    if pending:
        return "index_mutation_pending"
    return "complete" if complete else "legacy_index_required"


def _no_index(owner_dir: Path) -> dict:
    complete = not _proposal_json_names(owner_dir, stop_after=1)
    recovery = recovery_required(owner_dir)
    return {"rows": [], "index_complete": complete and recovery is None,
            "list_status": "recovery_required" if recovery else _status(complete),
            "inspected_index_rows": 0, "recovery_required": recovery,
            "coverage_scope": "maintained_index"}


def query_proposal_index(owner_dir: Path | None, state: str, now, cursor, limit: int) -> dict:
    if owner_dir is None:
        return {"rows": [], "index_complete": True, "list_status": "complete",
                "inspected_index_rows": 0, "recovery_required": None,
                "coverage_scope": "maintained_index"}
    if not _index_path(owner_dir).exists():
        return _no_index(owner_dir)
    recovery = recovery_required(owner_dir)
    decided = state == "decided_recent"
    after = _parse_cursor(cursor, decided)
    params: list[object]
    if decided:
        cutoff = _utc_text(now.replace(microsecond=0) - timedelta(
            seconds=DECIDED_RECENT_SECONDS))
        where = "proposal_state IN ('approved','rejected') AND decided_at>=?"
        params = [cutoff]
        if after:
            where += " AND (decided_at<? OR (decided_at=? AND proposal_ref>?))"
            params += [after[0], after[0], after[1]]
        order = "decided_at DESC, proposal_ref ASC"
    else:
        where = "expires_at>?"
        params = [_utc_text(now)]
        if state == "pending":
            where += " AND proposal_state='prepared'"
        else:
            where += " AND proposal_state IN ('prepared','approved')"
        if after:
            where += " AND (expires_at>? OR (expires_at=? AND proposal_ref>?))"
            params += [after[0], after[0], after[1]]
        order = "expires_at ASC, proposal_ref ASC"
    try:
        conn = _connect(owner_dir)
        try:
            pending = _pending_mutations(conn)
            complete = _meta_complete(conn) and not pending and recovery is None
            rows = conn.execute(f"""
              SELECT proposal_ref,record_sha256,proposal_state,expires_at,
                     indexed_at,decided_at,record_file FROM proposal_index
              WHERE {where} ORDER BY {order} LIMIT ?""",
                                (*params, limit)).fetchall()
        finally:
            conn.close()
    except (OSError, sqlite3.Error, ValueError):
        return {"rows": [], "index_complete": False,
                "list_status": "index_unavailable", "recovery_required": recovery,
                "coverage_scope": "maintained_index", "inspected_index_rows": 0}
    keys = ("proposal_ref", "record_sha256", "proposal_state", "expires_at",
            "indexed_at", "decided_at", "record_file")
    mapped = [dict(zip(keys, row)) for row in rows]
    for row in mapped:
        row["cursor"] = _cursor(row, decided)
    status = "recovery_required" if recovery else _status(complete, pending)
    return {"rows": mapped, "index_complete": complete,
            "list_status": status, "recovery_required": recovery,
            "coverage_scope": "maintained_index", "inspected_index_rows": len(mapped)}
