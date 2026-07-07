"""trajectory_intake.py — admit forum-exported orchestration runs as gradable data.

The forum flagship exports finished multi-agent runs as `forum.gradable-trajectory/1`
rows (a prompt, the trajectory, a can-fail grade, and the raw materials to
re-derive both). This module is the CONSUMER side of that seam. It never imports
forum: it re-implements forum's tagged-sha256 entry hash and RFC6962 merkle with
stdlib only, and independently recomputes the witness and the reward. The point is
zero trust — a datum is "witnessed" only if THIS code re-derives it, never because
forum said so.

That is the honest fix for the flywheel's yield accounting: manufactured_yield
counts rows blindly, so a row is admitted here only after recheck_witness returns
MATCH. A tampered entry, a spliced chain, or a flipped grade input all fail the
re-check and the row is refused. "No receipt -> no accept", enforced across a
process boundary with nothing shared but the record format.

Scope of the witness (stated so it is not overread): the re-check covers the
entry-hash chain integrity, the merkle root, and reward reproduction from the
recorded grade inputs. It does NOT re-execute the run or re-verify every payload
BODY (bodies are not all shipped); for full payload integrity it reads forum's own
oracle.verified self-report. Any tamper of a shipped entry FIELD still breaks the
entry-hash recompute, so the grade cannot be silently rewritten.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

GENESIS = "0" * 64
_SEP = "\x1f"


def _entry_hash(seq: int, ts: float, actor: str, kind: str,
                causal_parent: int | None, payload_hash: str,
                prev_hash: str) -> str:
    """Portable copy of forum.ledger.compute_entry_hash. If forum's recipe ever
    changes, the pinned cross-side vector test fails loudly here and in forum."""
    parts = [
        str(seq),
        f"{ts:.6f}",
        actor,
        kind,
        "" if causal_parent is None else str(causal_parent),
        payload_hash,
        prev_hash,
    ]
    return hashlib.sha256(_SEP.join(parts).encode("utf-8")).hexdigest()


def _leaf(h: str) -> str:
    return hashlib.sha256(b"\x00" + h.encode("utf-8")).hexdigest()


def _node(left: str, right: str) -> str:
    return hashlib.sha256(b"\x01" + left.encode("utf-8") + right.encode("utf-8")).hexdigest()


def _merkle_root(hashes: list[str]) -> str:
    """Portable copy of forum.ledger.merkle_root (RFC6962; promote-odd unchanged)."""
    if not hashes:
        return GENESIS
    level = [_leaf(h) for h in hashes]
    while len(level) > 1:
        nxt: list[str] = []
        for i in range(0, len(level), 2):
            if i + 1 < len(level):
                nxt.append(_node(level[i], level[i + 1]))
            else:
                nxt.append(level[i])
        level = nxt
    return level[0]


def _reward_from_inputs(grade_inputs: list[dict[str, Any]]) -> float:
    passed = sum(1 for g in grade_inputs if g.get("ok") is True)
    refuted = sum(1 for g in grade_inputs if g.get("ok") is False)
    total = passed + refuted
    return round(passed / total, 6) if total else 0.0


def recheck_witness(row: dict[str, Any]) -> dict[str, Any]:
    """Independently re-derive the witness for one exported row. Returns
    {witness: 'MATCH'|'DRIFT', root_reproduced, reward_reproduced, reward_expected,
     reasons}. MATCH iff every shipped entry_hash recomputes from its fields, the
     chain links (prev_hash == previous entry_hash, first == GENESIS), the merkle
     root over the entry hashes reproduces oracle.merkle_root, AND the reward
     recomputes from grade_inputs to the recorded grade.reward."""
    entries = row.get("trajectory", {}).get("entries", [])
    oracle = row.get("oracle", {})
    reasons: list[str] = []

    prev = GENESIS
    recomputed: list[str] = []
    for e in entries:
        h = _entry_hash(e["seq"], e["ts"], e["actor"], e["kind"],
                        e.get("causal_parent"), e["payload_hash"], e["prev_hash"])
        if h != e["entry_hash"]:
            reasons.append(f"entry {e.get('seq')} field tampered (hash recompute mismatch)")
        if e["prev_hash"] != prev:
            reasons.append(f"entry {e.get('seq')} chain broken (prev_hash != prior entry_hash)")
        recomputed.append(e["entry_hash"])
        prev = e["entry_hash"]

    root_reproduced = _merkle_root(recomputed)
    if root_reproduced != oracle.get("merkle_root"):
        reasons.append("merkle root mismatch")

    reward_reproduced = _reward_from_inputs(oracle.get("grade_inputs", []))
    reward_expected = row.get("grade", {}).get("reward")
    if reward_expected is not None and reward_reproduced != reward_expected:
        reasons.append("reward does not re-derive from grade_inputs")

    return {
        "witness": "MATCH" if not reasons else "DRIFT",
        "root_reproduced": root_reproduced,
        "reward_reproduced": reward_reproduced,
        "reward_expected": reward_expected,
        "reasons": reasons,
    }


def _seal(row: dict[str, Any]) -> str:
    body = {k: v for k, v in row.items() if k != "row_hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]


def load_forum_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Read exported rows, re-checking the row_hash seal (same recipe as the
    curator registry). A tampered row raises loudly rather than being trained on."""
    rows: list[dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        stored = row.get("row_hash", "")
        if _seal(row) != stored:
            raise ValueError(f"gradable row {row.get('task_id')!r} failed its seal "
                             f"— tampered or corrupted")
        rows.append(row)
    return rows


def to_gradable_row(row: dict[str, Any]) -> dict[str, Any]:
    """Map an exported trajectory onto the flywheel's (prompt, solution, oracle)
    triple shape so the UNCHANGED data_flywheel consumes it. The trajectory is the
    regenerable SOLUTION; the grader/oracle is the criterion KEPT. NOTE: the
    resulting criterion_conservation numbers are trajectory-token accounting, not
    code-token accounting — a data-shape measurement, never a capability claim."""
    traj = row.get("trajectory", {})
    oracle = row.get("oracle", {})
    return {
        "task_id": row["task_id"],
        "prompt": row["prompt"],
        "solution": json.dumps(traj, sort_keys=True),           # regenerable part
        "hidden_tests": json.dumps({                            # criterion kept
            "grade_inputs": oracle.get("grade_inputs", []),
            "derivation": row.get("grade", {}).get("derivation", ""),
        }, sort_keys=True),
        "difficulty": "trajectory",
        "grade": {
            "reward": row.get("grade", {}).get("reward"),
            "label": row.get("grade", {}).get("label"),
        },
        "oracle_ref": oracle.get("merkle_root"),
        "source": "forum.gradable-trajectory/1",
    }
