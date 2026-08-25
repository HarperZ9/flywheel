"""reward_dataset.py -- the receipt-to-reward training bridge.

Verified bench attempts are gate-decided training signals: prompt,
proposal, and a 1.0/0.0 reward minted from the gate's verdict. The
reward never comes from a model's judgment, an attempt without a gate
reference is dropped (a reward without evidence is a fabrication), and
identical prompt-proposal pairs deduplicate so the gradient is not
skewed. Output is GRPO/QLoRA-ready JSONL bound to the bench hash it
came from, on-device, no cloud.
"""
from __future__ import annotations

import json
from pathlib import Path

SCHEMA = "flywheel.reward-dataset/v1"


def rewards_from_bench(bench: dict, *, proposals: dict[str, str],
                       task_prompts: dict[str, str] | None = None) -> list[dict]:
    """Mint rewards from a verified bench. `proposals` maps an attempt's
    proposed_sha256 to the proposal text (the bench stores hashes, not
    text, so the caller supplies what it kept). `task_prompts` maps a
    task_id to the task's real prompt text -- the stronger training
    signal; without it the prompt falls back to the task id. Attempts
    without a gate reference are dropped: no evidence, no reward."""
    attempts = bench.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        raise ValueError("rewards come from a bench with attempts")
    task_prompts = task_prompts or {}
    rewards = []
    seen_pairs: set[tuple] = set()
    for attempt in attempts:
        gate_ref = str(attempt.get("gate_ref", ""))
        proposed_sha = str(attempt.get("proposed_sha256", ""))
        text = proposals.get(proposed_sha)
        task_id = str(attempt.get("task_id", ""))
        if not gate_ref:
            continue
        if text is None:
            continue
        prompt = task_prompts.get(task_id, f"task {task_id}")
        pair = (prompt, text)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        rewards.append({
            "prompt": prompt,
            "completion": text,
            "reward": 1.0 if attempt.get("gate_pass") else 0.0,
            "gate_ref": gate_ref,
            "endpoint": str(attempt.get("endpoint", "")),
            "bench_sha256": str(bench.get("bench_sha256", "")),
            "proposed_sha256": proposed_sha,
        })
    return rewards


def to_grpo_jsonl(rewards: list[dict], *,
                  out_path: Path | str) -> Path:
    """Emit GRPO/QLoRA-ready JSONL: one row per reward, each carrying a
    meta block that cites the gate receipt and bench hash."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    seen: set[tuple] = set()
    for r in rewards:
        pair = (r["prompt"], r["completion"])
        if pair in seen:
            continue
        seen.add(pair)
        rows.append({
            "prompt": r["prompt"],
            "completion": r["completion"],
            "reward": float(r["reward"]),
            "meta": {
                "bench_sha256": r["bench_sha256"],
                "gate_ref": r["gate_ref"],
                "endpoint": r["endpoint"],
                "proposed_sha256": r["proposed_sha256"],
                "schema": SCHEMA,
            },
        })
    out.write_text("\n".join(json.dumps(row, sort_keys=True)
                             for row in rows), encoding="utf-8")
    return out
