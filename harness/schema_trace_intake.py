"""schema_trace_intake.py — admit ARC-AGI-3 schema-harness trajectories as
gradable data.

Consumer side of an EXTERNAL seam (the schema-harness release format:
run.json + streamed events.jsonl per trajectory), mirroring the zero-trust
discipline of trajectory_intake: a trajectory is admitted only after THIS
code re-derives its grade from the raw events under the published RHAE
definition (per-level min(115, 100*(baseline/actions)^2), level-weighted,
completion-capped). Upstream logs are sequenced but not hash-chained, so the
tamper-evidence boundary is minted HERE: the events file is content-addressed
at import and recheck() re-derives both the address and the grade — an edited
log or an inflated score reads as DRIFT, never as data.

Nothing is imported from the upstream release; the scoring definition is
reimplemented from its published form so this side can fail independently.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

PER_LEVEL_CAP = 115.0
GAME_CAP = 100.0
SOURCE = "schema-harness.arc-agi-3/1"
_EFFORT = re.compile(r"(?:^|_)(minimal|low|medium|high|xhigh|max)(?:_|$)",
                     re.IGNORECASE)


class SchemaTraceError(RuntimeError):
    """A malformed or inconsistent trajectory: refused, never admitted."""


def stream_summary(events_path: str | Path) -> dict:
    """Stream one events.jsonl: per-level action counts (closed by level_up),
    the final state, and the file's content address. Enforces the published
    consistency rules — contiguous step_index, and a WIN may not leave
    unassigned actions — so a doctored log fails here."""
    completed: list[int] = []
    current = 0
    total = 0
    prev_step: int | None = None
    final_state: str | None = None
    last_action_state: str | None = None
    sha = hashlib.sha256()
    with Path(events_path).open("rb") as handle:
        for line_number, raw in enumerate(handle, start=1):
            sha.update(raw)
            line = raw.decode("utf-8").strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except ValueError as exc:
                raise SchemaTraceError(
                    f"{events_path}:{line_number}: invalid JSON: {exc}")
            kind = event.get("kind")
            if kind == "action_taken":
                step = event.get("step_index")
                expected = 0 if prev_step is None else prev_step + 1
                if step != expected:
                    raise SchemaTraceError(
                        f"{events_path}:{line_number}: non-contiguous "
                        f"step_index (expected {expected}, got {step})")
                prev_step = step
                total += 1
                current += 1
                if event.get("state") is not None:
                    last_action_state = str(event["state"]).upper()
                if event.get("level_up") is True:
                    completed.append(current)
                    current = 0
            elif kind == "run_finished" and event.get("state") is not None:
                final_state = str(event["state"]).upper()
    if total == 0:
        raise SchemaTraceError(f"{events_path}: no action_taken events")
    state = final_state or last_action_state or "UNKNOWN"
    if state == "NOT_FINISHED":
        state = "STOPPED"
    if state == "WIN" and current:
        raise SchemaTraceError(
            f"{events_path}: WIN with {current} unassigned actions")
    return {"completed": completed,
            "incomplete_actions": current or None,
            "total_actions": total, "state": state,
            "sha256": sha.hexdigest()}


def rhae(baseline_actions: list, completed_actions: list) -> tuple:
    """The published RHAE definition, reimplemented: per-level scores and the
    level-weighted, completion-capped game score."""
    if len(completed_actions) > len(baseline_actions):
        raise SchemaTraceError(
            f"completed {len(completed_actions)} levels but the baseline "
            f"defines only {len(baseline_actions)}")
    per_level = []
    for i, base in enumerate(baseline_actions):
        if i < len(completed_actions):
            per_level.append(min((base / completed_actions[i]) ** 2 * 100.0,
                                 PER_LEVEL_CAP))
        else:
            per_level.append(0.0)
    weights = list(range(1, len(baseline_actions) + 1))
    raw = sum(s * w for s, w in zip(per_level, weights)) / sum(weights)
    completed_weight = sum(range(1, len(completed_actions) + 1))
    cap = completed_weight / sum(weights) * GAME_CAP
    return per_level, min(raw, cap)


def load_trajectory(directory: str | Path, baselines: dict) -> dict:
    """One trajectory directory -> a re-derived record. `baselines` maps the
    short game name to its per-level baseline action counts. The grade here
    is OURS (recomputed), never copied from upstream metadata."""
    d = Path(directory)
    run = json.loads((d / "run.json").read_text(encoding="utf-8"))
    game = str(run.get("game_id", "")).split("-", 1)[0]
    if game not in baselines:
        raise SchemaTraceError(f"{d.name}: no baseline for game '{game}'")
    summary = stream_summary(d / "events.jsonl")
    per_level, game_score = rhae(baselines[game], summary["completed"])
    effort = _EFFORT.search(d.name)
    return {"game": game, "game_id": run.get("game_id"),
            "provider": run.get("provider"), "model": run.get("model"),
            "effort": effort.group(1).lower() if effort else "unknown",
            "state": summary["state"],
            "per_level_actions": summary["completed"],
            "incomplete_actions": summary["incomplete_actions"],
            "total_actions": summary["total_actions"],
            "per_level_rhae": [round(s, 2) for s in per_level],
            "rhae": round(game_score, 2),
            "baseline_actions": list(baselines[game]),
            "events_sha256": summary["sha256"]}


def to_gradable_row(traj: dict) -> dict:
    """Map onto the flywheel's (prompt, solution, criterion) triple, same as
    the forum intake: the trajectory is the regenerable SOLUTION, the RHAE
    inputs are the criterion KEPT, and the events content-address is the
    oracle_ref a recheck anchors to."""
    return {
        "task_id": f"arc-agi-3:{traj['game']}",
        "prompt": (f"Interactive ARC-AGI-3 game {traj['game_id']}: no rules "
                   "or goals are given; discover the mechanics and win every "
                   "level in as few actions as possible."),
        "solution": json.dumps({
            "per_level_actions": traj["per_level_actions"],
            "total_actions": traj["total_actions"],
            "state": traj["state"], "model": traj["model"],
            "effort": traj["effort"]}, sort_keys=True),
        "hidden_tests": json.dumps({
            "baseline_actions": traj["baseline_actions"],
            "derivation": "rhae: per-level min(115, 100*(baseline/actions)^2)"
                          ", level-weighted, completion-capped",
        }, sort_keys=True),
        "difficulty": "trajectory",
        "grade": {"reward": round(traj["rhae"] / GAME_CAP, 6),
                  "label": traj["state"]},
        "oracle_ref": traj["events_sha256"],
        "source": SOURCE,
    }


def recheck(row: dict, events_path: str | Path, baselines: dict) -> dict:
    """Independently re-derive one admitted row from the raw log on disk:
    the events content-address must equal oracle_ref and the reward must
    recompute from the baselines. Any mismatch is DRIFT with named reasons."""
    reasons: list = []
    game = str(row.get("task_id", "")).split(":", 1)[-1]
    try:
        summary = stream_summary(events_path)
        _, game_score = rhae(baselines.get(game, []), summary["completed"])
    except SchemaTraceError as exc:
        return {"witness": "DRIFT", "reasons": [f"re-derivation failed: {exc}"]}
    if summary["sha256"] != row.get("oracle_ref"):
        reasons.append("events file content-address mismatch")
    # derive under the SAME rounding as admission (rhae is rounded to 2
    # decimals before the reward is taken), or honest rows read as DRIFT
    reward = round(round(game_score, 2) / GAME_CAP, 6)
    if reward != row.get("grade", {}).get("reward"):
        reasons.append(f"reward does not re-derive "
                       f"(recomputed {reward}, recorded "
                       f"{row.get('grade', {}).get('reward')})")
    return {"witness": "MATCH" if not reasons else "DRIFT",
            "reward_reproduced": reward, "reasons": reasons}
