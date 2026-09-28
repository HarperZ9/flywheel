from __future__ import annotations

from typing import Any


PROJECTION_PROFILE = "inspect-json-v2-score-history-safe-provenance"
PROJECTION_DESCRIPTION = (
    "DERIVED allowlisted Inspect JSON: version/status/invalidated, eval "
    "task/model/config.limit, results counts/scorer coverage, sample "
    "id/epoch/status/error/score values and safe score edit provenance fields "
    "only; no prompts, messages, outputs, paths, timestamps outside score "
    "history provenance, metrics, run IDs, local metadata, score answers, score "
    "explanations, or score metadata."
)
PROJECTION_ALLOWLIST = [
    "/version", "/status", "/invalidated", "/eval/task", "/eval/model",
    "/eval/config/limit", "/results/total_samples",
    "/results/completed_samples", "/results/scores/*",
    "/samples/*/id", "/samples/*/epoch", "/samples/*/status",
    "/samples/*/error", "/samples/*/scores/*/value",
    "/samples/*/scores/*/reason",
    "/samples/*/scores/*/history/*/value",
    "/samples/*/scores/*/history/*/reason",
    "/samples/*/scores/*/history/*/provenance/author",
    "/samples/*/scores/*/history/*/provenance/reason",
    "/samples/*/scores/*/history/*/provenance/timestamp",
]


def project_inspect_log(source: dict[str, Any]) -> dict[str, Any]:
    projected = {k: source[k] for k in ("version", "status", "invalidated") if k in source}
    eval_obj = source.get("eval", {})
    projected["eval"] = {k: eval_obj[k] for k in ("task", "model") if k in eval_obj}
    if isinstance(eval_obj.get("config"), dict) and "limit" in eval_obj["config"]:
        projected["eval"]["config"] = {"limit": eval_obj["config"]["limit"]}
    results = source.get("results", {})
    projected["results"] = {k: results[k] for k in ("total_samples", "completed_samples") if k in results}
    if isinstance(results.get("scores"), list):
        projected["results"]["scores"] = [_project_result_score(item) for item in results["scores"]]
    projected["samples"] = [_project_sample(sample) for sample in source.get("samples", [])]
    return projected


def _project_result_score(item: dict[str, Any]) -> dict[str, Any]:
    return {k: item[k] for k in ("name", "scorer", "scored_samples", "unscored_samples") if k in item}


def _project_sample(sample: dict[str, Any]) -> dict[str, Any]:
    out = {k: sample[k] for k in ("id", "epoch", "status", "error") if k in sample}
    out["scores"] = {
        name: _project_score(score)
        for name, score in sample.get("scores", {}).items()
        if isinstance(score, dict) and "value" in score
    }
    return out


def _project_score(score: dict[str, Any]) -> dict[str, Any]:
    out = {"value": score["value"]}
    if "reason" in score:
        out["reason"] = score["reason"]
    if "history" in score:
        out["history"] = _project_history(score["history"])
    return out


def _project_history(history: Any) -> Any:
    if not isinstance(history, list):
        return history
    return [_project_history_event(item) for item in history]


def _project_history_event(item: Any) -> Any:
    if not isinstance(item, dict):
        return item
    out = {k: item[k] for k in ("value", "reason") if k in item}
    if "provenance" in item:
        out["provenance"] = _project_provenance(item["provenance"])
    return out


def _project_provenance(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    return {k: value[k] for k in ("timestamp", "author", "reason") if k in value}
