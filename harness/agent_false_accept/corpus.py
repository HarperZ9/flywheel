"""corpus.py -- turn episodes into (request, tool call, label, guard verdicts) records.

`condition` is a public label only: "baseline", "steered" or "random", plus
an ordinal `level` for the strength of the push. What produced a condition is
not recorded here.
"""
from __future__ import annotations

import hashlib
import json

from . import SCHEMA
from .flywheel_guards import FLYWHEEL_GUARDS
from .guards import GUARDS, consistency_score
from .labels import label

ALL_GUARDS = {**GUARDS, **FLYWHEEL_GUARDS}


def guard_verdicts(tool: str, args, intent: dict) -> dict:
    out = {}
    for gname, fn in ALL_GUARDS.items():
        try:
            out[gname] = fn(tool, args, intent)
        except Exception as exc:  # a guard that crashes is recorded, never read as a pass
            out[gname] = f"guard error: {type(exc).__name__}: {exc}"[:200]
    return out


def scores(call: dict, intent: dict, verdicts: dict) -> dict:
    """Graded scores for ROC: the consistency severity (0-3) and how many guards fired."""
    if not call["parse_ok"]:
        return {"consistency": 0, "guards_firing": 0}
    return {"consistency": consistency_score(call["tool"], call["args"], intent),
            "guards_firing": sum(1 for v in verdicts.values() if v)}


def record(call: dict, task: dict, condition: str, level: int, seed: int,
           episode: str) -> dict:
    intent = {**task["intent"], "request": task["request"]}
    lab = label(call["effects"], task) if call["parse_ok"] else {
        "destructive": False, "contradicts": False, "harmful": False,
        "unknown_effect": True, "why": ["unparseable call"]}
    verdicts = guard_verdicts(call["tool"], call["args"], intent) if call["parse_ok"] else {
        g: "unparseable" for g in ALL_GUARDS}
    body = {"schema": SCHEMA, "episode": episode, "task_id": task["id"], "split": task["split"],
            "condition": condition, "level": level, "seed": seed, "step": call["step"],
            "request": task["request"], "intent": task["intent"], "tool": call["tool"],
            "args": call["args"], "parse_ok": call["parse_ok"],
            "schema_error": call["schema_error"], "effects": call["effects"], **lab,
            "guards": verdicts, "scores": scores(call, intent, verdicts)}
    if not call["parse_ok"]:
        body["raw"] = call.get("raw", "")
    digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    return {"id": digest[:16], **body}


def episode_records(episodes, condition: str, level: int, tag: str) -> list[dict]:
    out = []
    for ep in episodes:
        eid = f"{tag}-{ep.task['id']}-s{ep.seed}"
        out.append({"type": "episode", "episode": eid, "task_id": ep.task["id"],
                    "split": ep.task["split"], "condition": condition, "level": level,
                    "seed": ep.seed, "n_calls": len(ep.calls), "final": ep.final[-300:]})
        out += [{"type": "call", **record(c, ep.task, condition, level, ep.seed, eid)}
                for c in ep.calls]
    return out
