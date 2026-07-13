"""corpus_export.py -- Gap E: the corpus->model handoff (operator-gated).

The loop's last open altitude is corpus->model: verified experience should
feed retraining. Per SUPERAPP.md boundaries, training start/hard-stop stay
operator-gated (never auto). So this module closes the PATH without closing
the AUTOMATION: it exports accepted PASS envelopes into a training-dataset
shard (JSONL of task+candidate+verdict, the raw material for a verified-RL
corpus) and emits a re-checkable receipt over the shard.

The operator then runs the existing gated training lane against the shard.
Nothing here auto-triggers a run. loop_closure marks this handoff:
  closed=True, verified=False -- the path is wired, the trigger is deliberately
  operator-gated (honest: not auto-verified end-to-end).

The receipt is a content-addressed manifest over the shard lines so a stranger
can re-derive what was exported without trusting the export step.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def export_corpus(envelopes_dir: str | Path, out_path: str | Path,
                  *, verdict_filter: str = "PASS") -> dict:
    """Read accepted envelopes, emit a JSONL shard of verified (task, candidate,
    verdict) triples, and return a re-checkable receipt over the shard.

    verdict_filter: only envelopes with this verdict are exported (default PASS;
    pass "" to export everything, useful for failure-corpus construction).
    """
    envelopes_dir = Path(envelopes_dir)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    exported = 0
    skipped = 0
    shard_hashes: list[str] = []
    h = hashlib.sha256()
    with out_path.open("w", encoding="utf-8") as f:
        for env_file in sorted(envelopes_dir.glob("*.json")):
            try:
                env = json.loads(env_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                skipped += 1
                continue
            verdict = env.get("verdict", "")
            if verdict_filter and verdict != verdict_filter:
                skipped += 1
                continue
            row = {
                "task_id": env.get("task_id", ""),
                "verdict": verdict,
                "candidate_sha256": env.get("candidate_sha256",
                                            env.get("candidate", {}).get("sha256", "")),
                "oracle_cmd": env.get("oracle_cmd", env.get("oracle", {}).get("cmd", "")),
                "content_hash": env.get("content_hash", ""),
                "source_envelope": env_file.name,
            }
            line = json.dumps(row, sort_keys=True)
            line_hash = hashlib.sha256(line.encode()).hexdigest()
            shard_hashes.append(line_hash)
            h.update(line_hash.encode())
            f.write(line + "\n")
            exported += 1
    receipt = {
        "schema": "flywheel.corpus-export/v1",
        "out_path": str(out_path),
        "envelopes_dir": str(envelopes_dir),
        "verdict_filter": verdict_filter,
        "exported": exported,
        "skipped": skipped,
        "shard_root_sha256": h.hexdigest() if exported else "",
        "note": ("verified-experience shard for retraining; the training START "
                 "remains operator-gated. Re-derive by hashing each JSONL line "
                 "and folding the line hashes into shard_root_sha256."),
    }
    return receipt


def verify_corpus_export(receipt: dict) -> str:
    """Re-derive the shard root hash from the shard file and compare. Returns
    MATCH / DRIFT / UNVERIFIABLE."""
    out_path = Path(receipt.get("out_path", ""))
    if not out_path.exists():
        return "UNVERIFIABLE"
    h = hashlib.sha256()
    count = 0
    for line in out_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        h.update(hashlib.sha256(line.encode()).hexdigest().encode())
        count += 1
    if receipt.get("exported", 0) != count:
        return "DRIFT"
    return "MATCH" if h.hexdigest() == receipt.get("shard_root_sha256") else "DRIFT"


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("usage: corpus_export.py <envelopes_dir> <out.jsonl> [verdict_filter]")
        sys.exit(2)
    r = export_corpus(sys.argv[1], sys.argv[2],
                      verdict_filter=sys.argv[3] if len(sys.argv) > 3 else "PASS")
    print(json.dumps(r, indent=2))
