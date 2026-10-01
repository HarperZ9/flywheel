"""witness.py -- detect a skipped hook and a rewritten store from outside the agent.

Two checks, both run by an owner process the agent did not start (a scheduled
task, a separate terminal, or a host-side process when the agent runs in an
OpenShell sandbox):

1. Chain-head export (W3). At every stop and every N records the hook copies
   the store's head (sequence number and seal) into the owner's witness
   directory, as a sealed, chained record of its own. check_heads() then finds
   any exported head the store no longer contains: a store rewritten after an
   export shows as DRIFT even when the rewrite is internally consistent.

2. Transcript join (W1). The harness writes its own transcript of every tool
   call the model emitted (Claude Code session JSONL, Codex rollout JSONL).
   The hook does not write those files. transcript_join() reads only the tool
   call items (tool_use, function_call, custom_tool_call, local_shell_call),
   never reasoning or thinking items, and joins their ids against the store's
   pre records. A tool call older than the grace window with no pre record is
   DRIFT: the hook was skipped, disabled or killed for that call.

Limits, stated where they bite: the witness directory and the transcripts sit
under the agent's OS user unless a sandbox boundary separates them, so an
agent with an unrestricted shell could edit both. The witness narrows the
residual from "a skipped hook leaves no trace" to "a skipped hook leaves a
trace unless the agent also rewrites the harness transcript and the witness
directory". The join assumes the hook event's tool_use_id equals the
transcript's tool call id (Claude Code tool_use.id, Codex call_id). The tests
use fixtures built on that assumption; it was not checked against a live
Claude Code or Codex session, and a mismatch would show as DRIFT on every
call, never as a silent MATCH.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .records import ALLOW_SCHEMA, HOLD_SCHEMA, REDEEM_SCHEMA, HoldStore

HEAD_SCHEMA = "flywheel.preaction-head/v1"
WITNESS_SCHEMA = "flywheel.preaction-witness/v1"
_PRE = (HOLD_SCHEMA, ALLOW_SCHEMA, REDEEM_SCHEMA)
_CALL_ITEMS = ("tool_use", "function_call", "custom_tool_call", "local_shell_call")
DOES_NOT_PROVE = ("A MATCH shows every tool call in the transcripts read had a pre record and "
                  "every exported head is still in the store. It does not show that the "
                  "transcripts are complete or unedited, or that the monitor judged well.")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _store_id(home) -> str:
    return os.path.realpath(str(home))


def export_head(home, witness_dir, *, clock=None) -> dict:
    """Append the store's current head to the witness directory's own chain."""
    head_hex, seq = HoldStore(home)._head()
    # head_seq, not store_seq: the witness store's own append sets store_seq
    # for its chain, which would overwrite the exported sequence number.
    rec = {"schema": HEAD_SCHEMA, "source": f"head:{seq}", "store": _store_id(home),
           "head_seq": seq, "head_sha256": head_hex, "exported_at": (clock or _now)()}
    HoldStore(witness_dir).append(rec)
    return rec


def check_heads(home, witness_dir) -> dict:
    """Every head exported for this store must still be in it, at its sequence."""
    heads = [r for r in HoldStore(witness_dir).read_all(tolerant=True)
             if r.get("schema") == HEAD_SCHEMA and r.get("store") == _store_id(home)]
    by_seq = {int(r.get("store_seq", 0)): r.get("seal", {}).get("hex", "")
              for r in HoldStore(home).read_all(tolerant=True)}
    findings = []
    for h in heads:
        seq = int(h.get("head_seq", 0))
        if seq == 0:
            continue
        if seq not in by_seq:
            findings.append({"cause": "EXPORTED_HEAD_MISSING", "head_seq": seq})
        elif by_seq[seq] != h.get("head_sha256"):
            findings.append({"cause": "EXPORTED_HEAD_REWRITTEN", "head_seq": seq})
    verdict = "DRIFT" if findings else ("MATCH" if heads else "UNVERIFIABLE")
    return {"verdict": verdict, "heads": len(heads), "findings": findings}


def _items(obj) -> list:
    """Tool call items in one transcript line, from either harness shape."""
    out = []
    msg = obj.get("message") if isinstance(obj.get("message"), dict) else None
    content = msg.get("content") if msg else None
    if isinstance(content, list):
        out += [c for c in content if isinstance(c, dict) and c.get("type") == "tool_use"]
    payload = obj.get("payload") if isinstance(obj.get("payload"), dict) else None
    if payload and payload.get("type") in _CALL_ITEMS[1:]:
        out.append(payload)
    return out


def transcript_calls(path) -> tuple:
    """(calls, sha256, malformed) for one transcript file. Each call is
    {id, name, timestamp}. Reasoning and thinking items are never read."""
    raw = Path(path).read_bytes()
    calls, malformed = [], 0
    for line in raw.decode("utf-8", "replace").splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            malformed += 1
            continue
        if not isinstance(obj, dict):
            continue
        for item in _items(obj):
            cid = item.get("id") or item.get("call_id")
            if cid:
                calls.append({"id": str(cid), "name": str(item.get("name", "")),
                              "timestamp": str(obj.get("timestamp", ""))})
    return calls, hashlib.sha256(raw).hexdigest(), malformed


def _older_than(ts: str, cutoff: datetime) -> bool:
    try:
        t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return True          # an unparseable time cannot claim to be recent
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t <= cutoff


def transcript_join(home, transcripts, *, grace_seconds: int = 60, now: str = "") -> dict:
    """Join transcript tool calls against pre records. DRIFT on any call older
    than the grace window with no pre record; UNVERIFIABLE with no readable
    transcript."""
    pre = {r.get("tool_use_id") for r in HoldStore(home).read_all(tolerant=True)
           if r.get("schema") in _PRE and r.get("tool_use_id")}
    cutoff = datetime.fromisoformat((now or _now()).replace("Z", "+00:00")) \
        - timedelta(seconds=grace_seconds)
    files, seen, orphans, recent, malformed = [], 0, [], 0, 0
    for path in transcripts:
        try:
            calls, digest, bad = transcript_calls(path)
        except OSError:
            continue
        files.append({"path_sha256": hashlib.sha256(str(path).encode()).hexdigest()[:16],
                      "sha256": digest, "calls": len(calls)})
        malformed += bad
        for c in calls:
            seen += 1
            if c["id"] in pre:
                continue
            if _older_than(c["timestamp"], cutoff):
                orphans.append({"id": c["id"], "name": c["name"]})
            else:
                recent += 1
    verdict = "UNVERIFIABLE" if not files else ("DRIFT" if orphans else "MATCH")
    return {"verdict": verdict, "files": files, "seen": seen, "orphans": orphans,
            "within_grace": recent, "malformed_lines": malformed}


def run_witness(home, witness_dir, transcripts, *, grace_seconds=60, now="") -> dict:
    """Both checks, combined, written as one sealed witness record."""
    heads = check_heads(home, witness_dir)
    join = transcript_join(home, transcripts, grace_seconds=grace_seconds, now=now)
    verdicts = {heads["verdict"], join["verdict"]}
    verdict = "DRIFT" if "DRIFT" in verdicts else (
        "MATCH" if verdicts == {"MATCH"} else "UNVERIFIABLE")
    rec = {"schema": WITNESS_SCHEMA, "source": f"witness:{now or _now()}",
           "store": _store_id(home), "verdict": verdict, "heads": heads,
           "transcripts": join, "observed_at": now or _now(),
           "does_not_prove": DOES_NOT_PROVE}
    HoldStore(witness_dir).append(rec)
    return rec
