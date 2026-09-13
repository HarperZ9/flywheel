from __future__ import annotations

from typing import Any

from .inspect_evidence_fields import (
    InspectImportError,
    _add,
    _escape,
    _optional_int,
    _optional_str,
    _score_value,
)

MAX_SCORE_HISTORY_EVENTS = 128
MAX_SCORE_HISTORY_TEXT = 4096


def new_score_history_counts() -> dict[str, int]:
    return {"present": 0, "empty": 0, "missing": 0}


def _sample_scores(value: object, base: str, pointers: list[dict[str, Any]],
                   history_counts: dict[str, int]) -> list:
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
        score_base = f"{base}/{_escape(scorer)}"
        _add(pointers, f"{score_base}/value", reported)
        entry: dict[str, Any] = {"scorer": scorer, "value": reported}
        if "reason" in score:
            reason = _history_text(score["reason"], f"{score_base}/reason",
                                   optional=True)
            _add(pointers, f"{score_base}/reason", reason)
        history = _score_history(score, score_base, pointers, history_counts)
        if history is not None:
            entry["score_history"] = history
        scores.append(entry)
    return scores


def _score_history(score: dict, base: str, pointers: list[dict[str, Any]],
                   counts: dict[str, int]) -> dict | None:
    if "history" not in score:
        counts["missing"] += 1
        return None
    history = score["history"]
    pointer = f"{base}/history"
    if type(history) is not list:
        raise InspectImportError("score history must be an array")
    if not history:
        counts["empty"] += 1
        _add(pointers, pointer, [])
        return {"state": "empty", "events": []}
    if len(history) > MAX_SCORE_HISTORY_EVENTS:
        raise InspectImportError("score history exceeds supported event limit")
    counts["present"] += 1
    return {
        "state": "present",
        "events": [
            _history_event(item, f"{pointer}/{index}", pointers)
            for index, item in enumerate(history)
        ],
    }


def _history_event(item: object, pointer: str,
                   pointers: list[dict[str, Any]]) -> dict:
    if type(item) is not dict:
        raise InspectImportError("score history entries must be objects")
    event: dict[str, Any] = {}
    redacted = [key for key in ("answer", "explanation", "metadata") if key in item]
    if "value" in item:
        value = item["value"]
        if not _score_value(value):
            raise InspectImportError("score history value has unsupported structure")
        _add(pointers, f"{pointer}/value", value)
        event["value"] = value
    if "reason" in item:
        reason = _history_text(item["reason"], f"{pointer}/reason",
                               optional=True)
        _add(pointers, f"{pointer}/reason", reason)
        if reason is not None:
            event["reason"] = reason
    if "provenance" in item and item["provenance"] is not None:
        event["provenance"] = _provenance(
            item["provenance"], f"{pointer}/provenance", pointers)
    _validate_ignored_metadata(item.get("metadata"), f"{pointer}/metadata")
    if redacted:
        event["redacted_fields"] = redacted
    if not event:
        raise InspectImportError("score history entry has no supported fields")
    return event


def _provenance(value: object, pointer: str,
                pointers: list[dict[str, Any]]) -> dict[str, str]:
    if type(value) is not dict:
        raise InspectImportError("score history provenance must be an object")
    out: dict[str, str] = {}
    for key in ("timestamp", "author", "reason"):
        if key not in value:
            continue
        item = _history_text(value[key], f"{pointer}/{key}",
                             optional=(key == "reason"))
        _add(pointers, f"{pointer}/{key}", item)
        if item is not None:
            out[key] = item
    _validate_ignored_metadata(value.get("metadata"), f"{pointer}/metadata")
    return out


def _history_text(value: object, pointer: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if type(value) is not str:
        raise InspectImportError(f"{pointer} must be a string")
    if len(value) > MAX_SCORE_HISTORY_TEXT:
        raise InspectImportError(f"{pointer} exceeds supported length")
    return value


def _validate_ignored_metadata(value: object, pointer: str) -> None:
    if value is None or value == "UNCHANGED" or type(value) is dict:
        return
    raise InspectImportError(f"{pointer} has unsupported structure")


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
                if entry[key] is not None and entry[key] < 0:
                    raise InspectImportError("negative score count")
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
