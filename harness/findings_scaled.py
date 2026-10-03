"""findings_scaled.py -- findings reported between a trivial baseline and a ceiling.

A raw score says little until you know what a trivial method scores and what a
repeat of the measurement reaches. An artifact under `<run_root>/scaled/*.json`
(schema flywheel.scaled-score/v1) carries the score and both anchors, each with
its own source path and SHA-256:

  {"schema": "flywheel.scaled-score/v1", "key": "...", "claim": "...",
   "score": 0.61,
   "baseline": {"value": 0.458, "source": "...", "sha256": "..."},
   "ceiling":  {"value": 0.82,  "source": "...", "sha256": "..."}}

The finding shows a scaled value only when both anchors are present with their
source and hash. Anything missing gives "pending" and no number at all.
"""
from __future__ import annotations

from pathlib import Path

from .findings_stats import scaled

SCHEMA = "flywheel.scaled-score/v1"


def _anchor(data: dict, name: str):
    a = data.get(name)
    if not isinstance(a, dict):
        return None
    v = a.get("value")
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return None
    if not a.get("source") or not a.get("sha256"):
        return None
    return a


def scaled_value(data) -> tuple[str | None, str]:
    """(value text or None for pending, bounds text) for one artifact."""
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return None, "not a scaled-score artifact"
    score = data.get("score")
    base, ceil = _anchor(data, "baseline"), _anchor(data, "ceiling")
    if base is None or ceil is None or not isinstance(score, (int, float)):
        return None, "pending: score or an anchor (value, source, sha256) is missing"
    value = scaled(score, base["value"], ceil["value"])
    text = (f"{value:.3f} of the way from baseline {base['value']} to ceiling "
            f"{ceil['value']} (raw {score})")
    bounds = (f"baseline from {base['source']} sha256 {base['sha256'][:16]}; "
              f"ceiling from {ceil['source']} sha256 {ceil['sha256'][:16]}")
    return text, bounds


def scaled_findings(root: Path, load_and_hash, finding_cls, findings: list) -> None:
    """Append one finding per artifact under root/scaled, in name order."""
    folder = Path(root) / "scaled"
    if not folder.is_dir():
        return
    for p in sorted(folder.glob("*.json")):
        data, sha = load_and_hash(p)
        key = f"scaled:{p.stem}"
        claim = data.get("claim", p.stem) if isinstance(data, dict) else p.stem
        try:
            value, bounds = scaled_value(data)
        except ValueError as exc:
            value, bounds = None, f"pending: {exc}"
        findings.append(finding_cls(key, claim, value, f"scaled/{p.name}", sha,
                                    bounds=bounds,
                                    status="measured" if value is not None else "pending"))
