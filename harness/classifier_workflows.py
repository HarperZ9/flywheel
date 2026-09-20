"""Shared advisory scoring adapter for independent workflow decisions.

Callers supply already-authorized eligibility and keep their existing fallback.
This adapter groups independent requests by family. It does not execute actions,
drop context, grant permissions, or turn experimental scores into selections.
"""
from __future__ import annotations

import copy
import json
import math
from collections import defaultdict

from .decision_contract import ID_PATTERN, evaluate_proposal, validate_request
from .evidence_json import canonical_sha256


class BaselineScorer:
    """Give the stdlib baseline the same batch interface as neural runtimes."""

    def __init__(self, model):
        self.model = model

    def score_batch(self, requests: list[dict], *, task_family: str) -> list[dict]:
        return self.model.predict_batch(requests, task_family=task_family)


def _bound_score(score: dict, request: dict, family: str) -> dict:
    if type(score) is not dict or score.get("request_sha256") != canonical_sha256(request):
        raise ValueError("score request binding mismatch")
    if score.get("task_family") != family or not isinstance(score.get("model_ref"), str):
        raise ValueError("score family or model binding mismatch")
    if not ID_PATTERN.fullmatch(score["model_ref"]):
        raise ValueError("invalid scorer model identity")
    expected = {c["id"] for c in request["choices"]}
    ids = score.get("candidate_ids")
    if type(ids) is not list or any(type(cid) is not str for cid in ids):
        raise ValueError("invalid score candidates")
    if len(ids) != len(set(ids)) or set(ids) not in (expected, expected | {"__abstain__"}):
        raise ValueError("score candidate binding mismatch")
    rows = score.get("scores")
    if type(rows) is not list or len(rows) != len(ids):
        raise ValueError("invalid score rows")
    seen, clean_rows = set(), []
    eligible = set(request["eligible_choice_ids"]) | {"__abstain__"}
    for row in rows:
        if type(row) is not dict or type(row.get("choice_id")) is not str:
            raise ValueError("invalid score row")
        cid = row["choice_id"]
        if cid not in ids or cid in seen or row.get("eligible") is not (cid in eligible):
            raise ValueError("score eligibility binding mismatch")
        seen.add(cid)
        clean = {"choice_id": cid, "eligible": cid in eligible}
        for key in ("score", "raw_logit", "probability_like"):
            value = row.get(key)
            if value is not None:
                if type(value) not in (int, float) or not math.isfinite(value):
                    raise ValueError("nonfinite score")
                if key == "probability_like" and not 0 <= value <= 1:
                    raise ValueError("invalid probability")
                if cid not in eligible and (key != "probability_like" or value != 0):
                    raise ValueError("ineligible score is not masked")
            clean[key] = value
        if cid in eligible and all(clean[k] is None for k in ("score", "raw_logit", "probability_like")):
            raise ValueError("missing eligible score")
        clean_rows.append(clean)
    return {"schema": "flywheel.classifier-shadow-scores/v1",
            "model_ref": score["model_ref"], "task_family": family,
            "request_sha256": canonical_sha256(request), "candidate_ids": list(ids),
            "scores": clean_rows, "calibration_status": "not_established",
            "automatic_selection_enabled": False}


def score_workflow_batch(packets: list[dict], scorer) -> list[dict]:
    """Score at most 256 independent decisions without changing their workflow."""
    if type(packets) is not list or len(packets) > 256:
        raise ValueError("invalid workflow decision batch")
    snapshots, groups = [], defaultdict(list)
    for packet in packets:
        if type(packet) is not dict or set(packet) != {"task_family", "request"}:
            raise ValueError("invalid workflow decision packet")
        family = packet["task_family"]
        if type(family) is not str or not ID_PATTERN.fullmatch(family):
            raise ValueError("invalid task family")
        snapshot = validate_request(packet["request"])
        groups[family].append(len(snapshots))
        snapshots.append((family, snapshot))
    bound = {}
    for family, indexes in groups.items():
        requests = [copy.deepcopy(snapshots[index][1]) for index in indexes]
        try:
            scores = scorer.score_batch(requests, task_family=family)
            if type(scores) is not list or len(scores) != len(indexes):
                raise ValueError("scorer result count mismatch")
            checked = [_bound_score(score, snapshots[index][1], family)
                       for score, index in zip(scores, indexes)]
            bound.update(zip(indexes, checked))
        except Exception:
            # Preserve the caller's fallback and avoid leaking runtime errors.
            continue
    result = []
    for index, (family, snapshot) in enumerate(snapshots):
        score = bound.get(index)
        result.append({
            "schema": "flywheel.classifier-workflow-shadow/v1",
            "task_family": family, "request_sha256": canonical_sha256(snapshot),
            "status": "scored_shadow" if score is not None else "scorer_unavailable",
            "scores": score, "fallback_required": True,
            "proposal": evaluate_proposal(snapshot, json.dumps({
                "choice_id": None, "evidence_refs": []}), scorer_ref="classifier-shadow"),
            "does_not_prove": "Decision correctness, authorization, calibration, or workflow speedup.",
        })
    return result
