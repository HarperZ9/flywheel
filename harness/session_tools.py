"""session_tools.py: browse, resume, and export past verified runs.

Quality-of-life OVER the existing receipt store, not a new store. run_loop
writes every accepted ProofEnvelope into envelopes_dir as
`{task_id}-{content_hash}.json` (loop.py). These helpers read that directory:

  - list_sessions   : one compact row per envelope file.
  - get_session     : the full envelope dict(s) for a task_id, or None.
  - resume_context  : the verified-fact handles a resume would rehydrate into a
                      VerifiedPool (evolutionary_flywheel.VerifiedPool.facts
                      shape), computed from the store, not re-run.
  - export_transcript: a deterministic, offline-verifiable, redacted bundle.
  - engine_status   : a presence-only summary (domains, providers, sessions).

Trace hygiene (load-bearing): export_transcript and engine_status never emit a
secret, key, token, or absolute path. Redaction is the point of the export, and
it is enforced by test. Values under secret/key/token/authorization/password
keys are dropped, absolute paths are scrubbed, and raw candidate code is carried
only as a sha256.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import fields as _dc_fields
from pathlib import Path

from .envelope import ProofEnvelope
from .receipt_fields import canonical

EXPORT_SCHEMA = "flywheel.transcript-export/v1"
STATUS_SCHEMA = "flywheel.engine-status/v1"

# The families default_registry() registers (loop's oracle_registry: PytestOracle
# -> "code", LeanOracle -> "math"). Used only as the fallback when that module is
# not importable in a given checkout; the live registry wins whenever present.
_DEFAULT_DOMAINS = ("code", "math")

_REDACTED = "[redacted]"
_REDACTED_PATH = "[redacted-path]"
_SENSITIVE = ("secret", "token", "authorization", "password", "passwd", "apikey")
# A Windows absolute path anywhere inside a string (drive + separator + tail).
_WIN_PATH = re.compile(r"[A-Za-z]:[\\/][^\s\"']*")

_ENV_FIELDS = tuple(f.name for f in _dc_fields(ProofEnvelope))


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_raw(path: Path) -> dict | None:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


def _content_hash_of(raw: dict, path: Path) -> str:
    """The 16-hex content id. Recomputed from the envelope for integrity (a file
    whose body was tampered but whose name kept the old hash shows its real
    hash). Falls back to the filename suffix for a foreign / partial record."""
    try:
        known = {k: raw[k] for k in _ENV_FIELDS if k in raw}
        return ProofEnvelope(**known).content_hash()
    except (TypeError, ValueError):
        stem = Path(path).stem
        return stem.rsplit("-", 1)[-1] if "-" in stem else stem


def _iter_files(envelopes_dir) -> list[Path]:
    if envelopes_dir is None:
        return []
    d = Path(envelopes_dir)
    if not d.is_dir():
        return []
    return sorted(d.glob("*.json"))


def _rows(envelopes_dir) -> list[tuple[Path, dict, str]]:
    out = []
    for p in _iter_files(envelopes_dir):
        raw = _load_raw(p)
        if raw is None:
            continue
        out.append((p, raw, _content_hash_of(raw, p)))
    return out


def list_sessions(envelopes_dir) -> list[dict]:
    """One compact row per envelope file. Tolerant of a missing or empty dir
    (returns []). Sorted stably by (task_id, content_hash, path)."""
    rows = []
    for p, raw, ch in _rows(envelopes_dir):
        verdict = str(raw.get("verdict", ""))
        rows.append({
            "task_id": str(raw.get("task_id", "")),
            "verdict": verdict,
            "model_ref": str(raw.get("model_ref", "")),
            "content_hash": ch,
            # Only accepted envelopes are written to envelopes_dir (loop.py), so a
            # present PASS is an accepted result; anything else is a stray record.
            "accepted": verdict == "PASS",
            "path": str(p),
        })
    rows.sort(key=lambda r: (r["task_id"], r["content_hash"], r["path"]))
    return rows


def get_session(envelopes_dir, task_id: str):
    """The full envelope dict(s) for task_id, or None if unknown. A single dict
    when one record matches, a list (content-hash ordered) when several do."""
    matches = [(raw, ch) for _, raw, ch in _rows(envelopes_dir)
               if str(raw.get("task_id", "")) == task_id]
    if not matches:
        return None
    matches.sort(key=lambda t: t[1])
    if len(matches) == 1:
        return matches[0][0]
    return [raw for raw, _ in matches]


def resume_context(envelopes_dir, task_id: str):
    """The verified facts a resume would rehydrate: the accepted envelope's
    content-hash handle in VerifiedPool.facts shape ({task_id: "envelope:<hash>"},
    the exact handle loop.py banks). Seed a pool with VerifiedPool(facts=...); no
    loop is run here. Returns None when task_id has no accepted envelope."""
    handles: dict[str, str] = {}
    for _, raw, ch in sorted(_rows(envelopes_dir), key=lambda t: t[2]):
        if str(raw.get("task_id", "")) != task_id:
            continue
        if str(raw.get("verdict", "")) != "PASS":
            continue
        handles[str(raw.get("task_id", ""))] = f"envelope:{ch}"
    return handles or None


def _is_sensitive_key(name: str) -> bool:
    ln = str(name).lower()
    if any(marker in ln for marker in _SENSITIVE):
        return True
    return ln == "key" or ln.endswith("_key") or ln.startswith("key_")


def _redact_path(s: str) -> str:
    if _WIN_PATH.search(s):
        return _WIN_PATH.sub(_REDACTED_PATH, s)
    # A POSIX absolute filesystem path: leading "/", at least two segments, no
    # space, and not a URL. This spares "/v1"-style fragments and "https://...".
    if s.startswith("/") and "://" not in s and " " not in s and s.count("/") >= 2:
        return _REDACTED_PATH
    return s


def _redact(obj):
    if isinstance(obj, dict):
        return {k: (_REDACTED if _is_sensitive_key(k) else _redact(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact(v) for v in obj]
    if isinstance(obj, str):
        return _redact_path(obj)
    return obj


def _to_entry(raw: dict, ch: str, *, redacted: bool) -> dict:
    entry = dict(raw)
    entry["content_hash"] = ch
    if redacted:
        cand = entry.pop("candidate", None)
        if cand is not None:
            payload = cand if isinstance(cand, str) else canonical(cand)
            entry["candidate_sha256"] = "sha256:" + _sha256_hex(payload)
        entry = _redact(entry)
    return entry


def export_transcript(envelopes_dir, task_id: str, *, redacted: bool = True) -> dict:
    """A deterministic, offline-verifiable bundle for task_id. bundle_digest =
    sha256 over canonical(entries); the hashed body carries no timestamp, so the
    same store yields the same digest every time. With redacted=True the entries
    carry no absolute path, no secret/key/token value, and the candidate only as
    a sha256."""
    entries = []
    for _, raw, ch in sorted(_rows(envelopes_dir), key=lambda t: t[2]):
        if str(raw.get("task_id", "")) != task_id:
            continue
        entries.append(_to_entry(raw, ch, redacted=redacted))
    return {
        "schema": EXPORT_SCHEMA,
        "task_id": task_id,
        "entries": entries,
        "bundle_digest": "sha256:" + _sha256_hex(canonical(entries)),
    }


def _registered_domains() -> list[str]:
    try:
        from .oracle_registry import default_registry
        return sorted(default_registry().domains())
    except Exception:
        return sorted(_DEFAULT_DOMAINS)


def engine_status(*, envelopes_dir=None) -> dict:
    """A presence-only summary: registered domains, provider count, session
    count. Counts and names only, never a secret or a path."""
    from . import providers
    domains = _registered_domains()
    session_count = len(list_sessions(envelopes_dir)) if envelopes_dir is not None else 0
    return {
        "schema": STATUS_SCHEMA,
        "domains": domains,
        "domain_count": len(domains),
        "provider_count": len(providers.REGISTRY),
        "session_count": session_count,
    }
