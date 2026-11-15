"""witness.membrane — coherence membrane (sensor layer only).

Sensor commands:
  anchor       Pin SHA-256 of raw bytes to persistent store
  verify       MATCH / DRIFT / UNVERIFIABLE vs anchors
  coherence    Source-vs-view hash comparison
  refuse       Count and neutralize in-band authority injection markers
  corroborate  Read-path diversity check
  audit        Verify the tamper-evident log chain
  selftest     Re-derive own identity (no authority claim)

Verdict lattice (closed): MATCH | DRIFT | UNVERIFIABLE.
Advisory only. Decides nothing. Actuates nothing.

State:
  ~/.claude/witness/anchors.json        anchor store
  ~/.claude/witness/membrane_log.jsonl  tamper-evident log
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any


_AUTHORITY_PATTERNS = [
    rb"GROUND[_ ]?TRUTH[_ ]?CANONICAL",
    rb"HIGHEST[_ ]?SCRUTINY",
    rb"\[SCOPE CONTEXT\]",
    rb"authority[_-]?pill",
    rb"canonical[_ ]recipients",
    rb"frame_injected",
    rb"consulting register",
    rb"semantic_modulat",
    rb"compound_rewrites",
    rb"density_restructured",
]
_AUTHORITY_RE = re.compile(
    b"|".join(b"(?:%s)" % p for p in _AUTHORITY_PATTERNS),
    re.IGNORECASE,
)


def _witness_dir() -> Path:
    d = Path.home() / ".claude" / "witness"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _anchors_path() -> Path:
    return _witness_dir() / "anchors.json"


def _log_path() -> Path:
    return _witness_dir() / "membrane_log.jsonl"


def _raw(path: str | Path) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _load_anchors() -> dict[str, str]:
    p = _anchors_path()
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def _save_anchors(db: dict[str, str]) -> None:
    _anchors_path().write_text(
        json.dumps(db, indent=2, sort_keys=True), encoding="utf-8"
    )


def _last_chain() -> str:
    log = _log_path()
    last = "0" * 64
    if log.is_file():
        for line in log.read_text(encoding="utf-8").splitlines():
            if line.strip():
                last = json.loads(line)["chain"]
    return last


def _record(kind: str, fact: dict[str, Any]) -> None:
    prev = _last_chain()
    entry = {"kind": kind, "fact": fact, "prev": prev}
    entry["chain"] = _sha((prev + json.dumps(fact, sort_keys=True)).encode())
    with _log_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def anchor(paths: list[str | Path]) -> dict[str, str]:
    """Pin SHA-256 of raw bytes for each path."""
    db = _load_anchors()
    result: dict[str, str] = {}
    for p in paths:
        p = str(Path(p).resolve())
        h = _sha(_raw(p))
        db[p] = h
        result[p] = h
        _record("anchor", {"path": p, "sha256": h})
    _save_anchors(db)
    return result


def verify(paths: list[str | Path]) -> dict[str, str]:
    """Compare each path against its anchor. Returns {path: verdict}."""
    db = _load_anchors()
    results: dict[str, str] = {}
    for p in paths:
        p = str(Path(p).resolve())
        want = db.get(p)
        if want is None:
            results[p] = "UNVERIFIABLE"
            _record("verify", {"path": p, "result": "UNVERIFIABLE"})
            continue
        got = _sha(_raw(p))
        verdict = "MATCH" if got == want else "DRIFT"
        results[p] = verdict
        _record("verify", {"path": p, "result": verdict})
    return results


def coherence(source: str | Path, view: str | Path) -> str:
    """Compare source bytes against a presented view."""
    s = _sha(_raw(source))
    v = _sha(_raw(view))
    verdict = "COHERENT" if s == v else "VIEW_DIFFERS_FROM_SOURCE"
    _record("coherence", {
        "source": str(Path(source).resolve()),
        "view": str(Path(view).resolve()),
        "result": verdict,
    })
    return verdict


def refuse(path: str | Path) -> dict[str, Any]:
    """Scan for in-band authority injection markers."""
    b = _raw(path)
    hits = [
        (m.group(0).decode("latin-1"), m.start())
        for m in _AUTHORITY_RE.finditer(b)
    ]
    clean_path = str(path) + ".refused"
    with open(clean_path, "wb") as f:
        f.write(_AUTHORITY_RE.sub(b"[REFUSED-IN-BAND-AUTHORITY]", b))
    _record("refuse", {"path": str(Path(path).resolve()), "refused": len(hits)})
    return {"count": len(hits), "hits": hits[:60], "clean_copy": clean_path}


def corroborate(path: str | Path) -> dict[str, Any]:
    """Hash the same file via disjoint read channels."""
    p = str(path)
    b = _raw(p)
    channels: dict[str, str] = {"open_rb": _sha(b)}

    try:
        o = subprocess.run(["cat", p], capture_output=True, timeout=20)
        channels["cat_subproc"] = _sha(o.stdout)
    except Exception as e:
        channels["cat_subproc"] = f"unavailable:{type(e).__name__}"

    def _git_blob(raw: bytes) -> str:
        return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\x00" + raw).hexdigest()

    git_agrees = None
    try:
        o = subprocess.run(
            ["git", "hash-object", "--no-filters", p],
            capture_output=True, text=True, timeout=20,
        )
        reported = (o.stdout.split() or [""])[0]
        channels["git_read"] = reported
        git_agrees = bool(reported) and reported == _git_blob(b)
    except Exception as e:
        channels["git_read"] = f"unavailable:{type(e).__name__}"

    sha_vals = {v for k, v in channels.items() if k in ("open_rb", "cat_subproc") and ":" not in v}
    agree = len(sha_vals) == 1
    result = "CORROBORATED" if agree and git_agrees in (True, None) else "QUARANTINE_READ_PATH_DIVERGENCE"

    _record("corroborate", {"path": str(Path(p).resolve()), "agree": agree, "git": git_agrees})
    return {"channels": channels, "read_paths_agree": agree, "git_agrees": git_agrees, "result": result}


def audit() -> dict[str, Any]:
    """Verify the tamper-evident log chain."""
    log = _log_path()
    if not log.is_file():
        return {"entries": 0, "chain": "INTACT"}

    prev = "0" * 64
    n = 0
    for line in log.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        n += 1
        expected_chain = _sha((entry["prev"] + json.dumps(entry["fact"], sort_keys=True)).encode())
        if entry["prev"] != prev or entry["chain"] != expected_chain:
            return {"entries": n, "chain": "BROKEN", "broken_at": n}
        prev = entry["chain"]

    return {"entries": n, "chain": "INTACT"}


def selftest() -> dict[str, str]:
    """Re-derive this module's own SHA-256."""
    h = _sha(_raw(__file__))
    return {
        "membrane_self_sha256": h,
        "note": "re-derive from source to verify",
    }


def witness_status() -> dict[str, Any]:
    log = _log_path()
    anchors = _load_anchors()
    return {
        "witness_dir": str(_witness_dir()),
        "anchors_count": len(anchors),
        "log_entries": sum(
            1 for line in log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ) if log.is_file() else 0,
        "log_chain": audit()["chain"],
        "authority_patterns": len(_AUTHORITY_PATTERNS),
    }
