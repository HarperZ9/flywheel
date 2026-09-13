import hashlib
from typing import Any

from .evidence_json import strict_load_json
from .inspect_evidence_fields import (
    InspectImportError,
    _add,
    _escape,
    _exact_bool,
    _exact_int,
    _exact_str,
    _json_scalar,
    _object,
    _optional_int,
    _optional_object,
    _optional_str,
    _sample_id,
    _score_value,
)

SCHEMA = "flywheel.inspect-evidence/v1"
MAX_BYTES = 16 * 1024 * 1024
STATUSES = {"started", "success", "cancelled", "error"}
SAMPLE_ERROR_STATUSES = {"error", "cancelled"}


def import_inspect_log(raw: bytes) -> dict:
    if type(raw) is not bytes:
        raise InspectImportError("Inspect log input must be bytes")
    source = {"sha256": hashlib.sha256(raw).hexdigest(), "byte_length": len(raw)}
    try:
        root = strict_load_json(raw, max_bytes=MAX_BYTES, max_depth=32)
        return _import_root(root, source)
    except InspectImportError:
        raise
    except (TypeError, ValueError) as exc:
        raise InspectImportError(str(exc)) from exc

def _import_root(root: dict, source: dict) -> dict:
    pointers: list[dict[str, Any]] = []
    version = _exact_int(root.get("version"), "/version")
    if version != 2:
        raise InspectImportError("Inspect log version must be 2")
    _add(pointers, "/version", version)

    status = _exact_str(root.get("status"), "/status")
    if status not in STATUSES:
        raise InspectImportError("unsupported Inspect log status")
    _add(pointers, "/status", status)
    invalidated = _invalidated(root, pointers)

    eval_obj = _object(root.get("eval"), "/eval")
    for key in ("task", "model", "run_id"):
        if key in eval_obj:
            value = _optional_str(eval_obj[key], f"/eval/{key}")
            _add(pointers, f"/eval/{key}", value)
    config_limit, config_pointer = _config_limit(eval_obj, pointers)
    reported_error = _error_summary(root.get("error"), "/error", pointers)
    top_error = "error" in root and root.get("error") is not None

    results = _optional_object(root.get("results"), "/results")
    total = _optional_int(results.get("total_samples"), "/results/total_samples")
    completed = _optional_int(results.get("completed_samples"), "/results/completed_samples")
    if "total_samples" in results:
        _add(pointers, "/results/total_samples", total)
    if "completed_samples" in results:
        _add(pointers, "/results/completed_samples", completed)
    _validate_counts(total, completed)

    samples_source = root.get("samples", None)
    if samples_source is None:
        if status == "success":
            raise InspectImportError("successful Inspect logs require samples")
        samples_source = []
    if type(samples_source) is not list:
        raise InspectImportError("samples must be an array")

    samples, sample_records, samples_with_scores, sample_error = _samples(
        samples_source, pointers)
    observed = len(samples)
    if total is not None and observed > total:
        raise InspectImportError("observed samples exceed total_samples")
    if status == "success" and completed is not None and completed > observed:
        raise InspectImportError("completed_samples exceed observed samples")

    result_scores = _result_scores(results, pointers, total)
    result_gap = _result_score_gap(samples, result_scores)
    coverage_complete = _coverage_complete(
        status, total, completed, observed, samples_with_scores,
        sample_error or top_error or invalidated,
        result_scores, result_gap)
    assessment = _assessment(status, coverage_complete, sample_error, top_error)
    counts = {
        "total_samples": total,
        "completed_samples": completed,
        "config_limit": config_limit,
        "config_limit_pointer": config_pointer,
        "observed_samples": observed,
    }
    scoring_coverage = {
        "coverage_complete": coverage_complete,
        "samples_with_scores": samples_with_scores,
        "sample_score_records": sample_records,
        "result_scores": result_scores,
    }
    return {
        "schema": SCHEMA,
        "source": source,
        "producer": {"format": "inspect-json", "version": version},
        "reported_status": status,
        "assessment": assessment,
        "invalidated": invalidated,
        "semantic_verification": "UNVERIFIABLE",
        "counts": counts,
        "scoring_coverage": scoring_coverage,
        "reported_error": reported_error,
        "samples": samples,
        "source_pointers": pointers,
        "does_not_prove": _does_not_prove(assessment, invalidated=invalidated),
    }

def _samples(items: list, pointers: list[dict[str, Any]]) -> tuple[list, int, int, bool]:
    seen = set()
    sanitized = []
    score_records = 0
    with_scores = 0
    has_error = False
    for index, item in enumerate(items):
        pointer = f"/samples/{index}"
        if type(item) is not dict:
            raise InspectImportError("sample entries must be objects")
        sample_id = _sample_id(item.get("id"), f"{pointer}/id")
        epoch = _exact_int(item.get("epoch"), f"{pointer}/epoch")
        key = ((type(sample_id).__name__, str(sample_id)), epoch)
        if key in seen:
            raise InspectImportError("duplicate sample id and epoch")
        seen.add(key)
        _add(pointers, f"{pointer}/id", sample_id)
        _add(pointers, f"{pointer}/epoch", epoch)

        status = _optional_str(item.get("status"), f"{pointer}/status")
        if "status" in item:
            _add(pointers, f"{pointer}/status", status)
        error_present = "error" in item and item.get("error") is not None
        error = _error_summary(item.get("error"), f"{pointer}/error", pointers)
        sample_scores = _sample_scores(item.get("scores"), f"{pointer}/scores", pointers)
        if sample_scores:
            with_scores += 1
            score_records += len(sample_scores)
        has_error = has_error or error_present or status in SAMPLE_ERROR_STATUSES
        sanitized.append({
            "id": sample_id,
            "epoch": epoch,
            "status": status,
            "error": error,
            "scores": sample_scores,
        })
    return sanitized, score_records, with_scores, has_error

def _sample_scores(value: object, base: str, pointers: list[dict[str, Any]]) -> list:
    if value is None:
        return []
    if type(value) is not dict:
        raise InspectImportError("sample scores must be an object")
    scores = []
    for scorer, score in value.items():
        if type(scorer) is not str:
            raise InspectImportError("score names must be strings")
        if type(score) is not dict:
            raise InspectImportError("score entries must be objects")
        if "value" not in score:
            raise InspectImportError("score entries require value")
        reported = score["value"]
        if not _score_value(reported):
            raise InspectImportError("score value has unsupported structure")
        _add(pointers, f"{base}/{_escape(scorer)}/value", reported)
        scores.append({"scorer": scorer, "value": reported})
    return scores

def _result_scores(results: dict, pointers: list[dict[str, Any]], total: int | None) -> list:
    value = results.get("scores")
    if value is None:
        return []
    if type(value) is not list:
        raise InspectImportError("results scores must be an array")
    coverage = []
    for index, item in enumerate(value):
        pointer = f"/results/scores/{index}"
        if type(item) is not dict:
            raise InspectImportError("results score entries must be objects")
        entry: dict[str, Any] = {}
        for key in ("name", "scorer"):
            if key in item:
                entry[key] = _optional_str(item[key], f"{pointer}/{key}")
                _add(pointers, f"{pointer}/{key}", entry[key])
        for key in ("scored_samples", "unscored_samples"):
            if key in item:
                entry[key] = _optional_int(item[key], f"{pointer}/{key}")
                if entry[key] is not None and entry[key] < 0: raise InspectImportError("negative score count")
                _add(pointers, f"{pointer}/{key}", entry[key])
        scored, unscored = entry.get("scored_samples"), entry.get("unscored_samples")
        if total is not None and (
            (scored is not None and scored > total)
            or (unscored is not None and unscored > total)
            or (scored is not None and unscored is not None and scored + unscored > total)
        ):
            raise InspectImportError("score coverage exceeds total_samples")
        coverage.append(entry)
    return coverage

def _config_limit(eval_obj: dict, pointers: list[dict[str, Any]]) -> tuple[object, str | None]:
    config = eval_obj.get("config")
    if config is None: return None, None
    if type(config) is not dict: raise InspectImportError("eval config must be an object")
    if "limit" not in config or config["limit"] is None: return None, None
    limit = config["limit"]
    if type(limit) is list and len(limit) == 2 and all(type(item) is int for item in limit):
        pass
    elif type(limit) is not int:
        raise InspectImportError("eval config limit must be integer or two-integer range")
    _add(pointers, "/eval/config/limit", limit)
    return limit, "/eval/config/limit"

def _result_score_gap(samples: list, result_scores: list) -> bool:
    gap = False
    for result in result_scores:
        scorer = result.get("scorer")
        if scorer is None:
            continue
        raw_count = 0
        distinct_ids = set()
        for sample in samples:
            matched = any(score["scorer"] == scorer for score in sample["scores"])
            raw_count += 1 if matched else 0
            if matched:
                distinct_ids.add((type(sample["id"]).__name__, str(sample["id"])))
            else:
                gap = True
        scored, unscored = result.get("scored_samples"), result.get("unscored_samples")
        if unscored not in (None, 0):
            gap = True
        allowed = {raw_count, len(distinct_ids)}
        if scored is not None and unscored is not None and scored + unscored not in allowed:
            raise InspectImportError("result score coverage contradicts sample scores")
        if scored is None or scored not in allowed:
            gap = True
    return gap

def _coverage_complete(status: str, total: int | None, completed: int | None,
                       observed: int, with_scores: int, sample_error: bool,
                       result_scores: list, result_gap: bool) -> bool:
    if status != "success" or sample_error or total is None or completed is None:
        return False
    if not (total == completed == observed) or (observed and with_scores != observed):
        return False
    if result_gap:
        return False
    return all(item.get("unscored_samples") in (None, 0) for item in result_scores)

def _assessment(status: str, coverage_complete: bool, sample_error: bool, top_error: bool) -> str:
    if status == "error" or top_error: return "error"
    return "incomplete" if status in {"started", "cancelled"} or sample_error or not coverage_complete else "reported"

def _invalidated(root: dict, pointers: list[dict[str, Any]]) -> bool:
    if "invalidated" not in root:
        return False
    invalidated = _exact_bool(root["invalidated"], "/invalidated")
    _add(pointers, "/invalidated", invalidated)
    return invalidated

def _does_not_prove(assessment: str, *, invalidated: bool = False) -> list[str]:
    reasons = [
        "Inspect status and scorer values are reported by the source log only.",
        "This import does not independently rerun the task, scorer, model, or dataset.",
        "A success status or score value is not independent semantic verification.",
    ]
    if invalidated:
        reasons.append("The source log is marked invalidated.")
    if assessment in {"incomplete", "error"}:
        reasons.append("The source log reports incomplete or error coverage.")
    return reasons

def _validate_counts(total: int | None, completed: int | None) -> None:
    for value, name in ((total, "total_samples"), (completed, "completed_samples")):
        if value is not None and value < 0:
            raise InspectImportError(f"{name} must not be negative")
    if total is not None and completed is not None and completed > total:
        raise InspectImportError("completed_samples exceed total_samples")

def _error_summary(value: object, pointer: str, pointers: list[dict[str, Any]]) -> object:
    if value is None:
        return None
    if _json_scalar(value):
        _add(pointers, pointer, value)
        return value
    if type(value) is dict and "message" in value and _json_scalar(value["message"]):
        _add(pointers, f"{pointer}/message", value["message"])
        return {"message": value["message"]}
    raise InspectImportError("error must be a scalar or object with scalar message")
