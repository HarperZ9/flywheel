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


def exception_type_name(exc: BaseException) -> str:
    """Name the exception class only. Its message can carry private runtime detail."""
    name = type(exc).__name__
    # A class built at runtime can carry arbitrary text in its name.
    return name if name.isidentifier() and len(name) <= 64 else "Exception"


def _score_family(scorer, family: str, snapshots: list[dict]) -> tuple[list, tuple]:
    """Score one family group; return (bound scores, (error type, error stage)).

    A failure keeps the caller's fallback. The record names which step failed and
    the exception class, so a stalled run can be told apart from a model that
    chose to abstain, while the exception text never leaves this adapter.
    """
    requests = [copy.deepcopy(snapshot) for snapshot in snapshots]
    try:
        scores = scorer.score_batch(requests, task_family=family)
    except Exception as exc:
        return [], (exception_type_name(exc), "score_batch")
    try:
        if type(scores) is not list or len(scores) != len(snapshots):
            raise ValueError("scorer result count mismatch")
        checked = [_bound_score(score, snapshot, family)
                   for score, snapshot in zip(scores, snapshots)]
    except Exception as exc:
        return [], (exception_type_name(exc), "binding")
    return checked, (None, None)


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
    bound, failures = {}, {}
    for family, indexes in groups.items():
        checked, failure = _score_family(scorer, family, [snapshots[i][1] for i in indexes])
        bound.update(zip(indexes, checked))
        failures.update((index, failure) for index in indexes)
    result = []
    for index, (family, snapshot) in enumerate(snapshots):
        score = bound.get(index)
        error_type, error_stage = failures[index]
        result.append({
            "schema": "flywheel.classifier-workflow-shadow/v1",
            "task_family": family, "request_sha256": canonical_sha256(snapshot),
            "status": "scored_shadow" if score is not None else "scorer_unavailable",
            "scorer_error_type": error_type, "scorer_error_stage": error_stage,
            "scores": score, "fallback_required": True,
            "proposal": evaluate_proposal(snapshot, json.dumps({
                "choice_id": None, "evidence_refs": []}), scorer_ref="classifier-shadow"),
            "does_not_prove": "Decision correctness, authorization, calibration, or workflow speedup.",
        })
    return result
