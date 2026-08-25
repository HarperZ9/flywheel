"""pm_roadmap.py -- the manager surface: one page a PM can read.

Goals are swarm goals; the decomposed work is each goal's children;
verification status is the sealed per-child receipt state. V1 reads
only what the platform already sealed (swarm receipts, bound skill
gates) and prints its own limits at the bottom of the page, because a
roadmap that hides what it does not know is a fiction with formatting.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from .evidence_json import canonical_sha256
from .skill_gate import load_skill_gates
from .subagent_roles import SWARM_SCHEMA
from .subagent_store import load_swarm_receipt

SCHEMA = "flywheel.pm-roadmap/v1"


def _goal_from_receipt(receipt: dict) -> dict:
    children = receipt.get("children", [])
    done = sum(1 for c in children if c.get("status") == "completed")
    return {
        "ref": receipt.get("swarm_id", ""),
        "goal_sha256": receipt.get("goal_sha256", ""),
        "endpoint": receipt.get("endpoint", ""),
        "state": "sealed",
        "verdict": receipt.get("verdict"),
        "verified_children": f"{done} of {len(children)}",
        "total": len(children),
        "children": [{"role": c.get("role"), "status": c.get("status")}
                     for c in children],
    }


def _goal_from_live(row: dict) -> dict:
    return {
        "ref": row.get("swarm_id", ""),
        "goal_sha256": "",
        "endpoint": "",
        "state": row.get("status", "unknown"),
        "verdict": None,
        "verified_children": None,
        "total": row.get("children", 0),
        "children": [],
    }


def build_pm_roadmap(*, swarms: list[dict], skills: list[dict],
                     generated_at: str) -> dict:
    goals = []
    for row in swarms:
        if row.get("schema") == SWARM_SCHEMA or (
                row.get("schema") is None and "children" in row
                and "verdict" in row):
            goals.append(_goal_from_receipt(row))
        else:
            goals.append(_goal_from_live(row))
    doc = {
        "schema": SCHEMA,
        "generated_at": generated_at,
        "goals": goals,
        "verification": {
            "skills_bound": len(skills),
            "sealed_goals": sum(1 for g in goals if g["state"] == "sealed"),
            "open_goals": sum(1 for g in goals if g["state"] != "sealed"),
        },
        "does_not_prove": [
            "a satisfied quorum attests children ran and reported; it "
            "does not prove the goal was achieved",
            "open rows are known-running or detached work, not estimates",
        ],
    }
    doc["roadmap_sha256"] = canonical_sha256(
        {k: v for k, v in doc.items() if k != "roadmap_sha256"})
    return doc


def render_markdown(doc: dict) -> str:
    lines = [f"# Roadmap -- {doc.get('generated_at', '')}", ""]
    lines.append("| Goal | State | Verified children | Verdict |")
    lines.append("|---|---|---|---|")
    for g in doc.get("goals", []):
        ref = str(g.get("ref", ""))
        short = ref[:14] + "..." if len(ref) > 14 else ref
        verdict = (g.get("verdict") or "-") if g.get("state") == "sealed" \
            else "-"
        lines.append(f"| {short} | {g.get('state', '?')} | "
                     f"{g.get('verified_children') or '-'} | {verdict} |")
    v = doc.get("verification", {})
    lines += ["", "## Verification floor", "",
              f"- skills bound: {v.get('skills_bound', 0)}",
              f"- sealed goals: {v.get('sealed_goals', 0)}",
              f"- open goals: {v.get('open_goals', 0)}"]
    lines += ["", "## Does not prove", ""]
    for note in doc.get("does_not_prove", []):
        lines.append(f"- {note}")
    return "\n".join(lines) + "\n"


def roadmap_from_run_root(run_root: Path) -> dict:
    root = Path(run_root)
    swarms: list[dict] = []
    sroot = root / "subagents"
    if sroot.is_dir():
        for entry in sorted(sroot.iterdir()):
            receipt = load_swarm_receipt(entry / "swarm.json")
            if receipt is not None:
                swarms.append(receipt)
                continue
            live = entry / "live.json"
            if live.is_file():
                kids = 0
                try:
                    import json
                    data = json.loads(live.read_text(encoding="utf-8"))
                    kids = len(data.get("children", []))
                except (OSError, ValueError):
                    pass
                swarms.append({"swarm_id": entry.name,
                               "status": "detached", "children": kids})
    skills = load_skill_gates(root / "skills" / "gates.jsonl")
    import time
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return build_pm_roadmap(swarms=swarms, skills=skills,
                            generated_at=stamp)


def goal_head(doc: dict) -> str:
    """Stable short ref for cross-linking: first goal's sha prefix."""
    for g in doc.get("goals", []):
        if g.get("goal_sha256"):
            return g["goal_sha256"][:12]
    return hashlib.sha256(doc.get("generated_at", "").encode()).hexdigest()[:12]
