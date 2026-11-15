"""Source-change review gates on top of Chorus's deterministic digest path.

This module compares two already-gathered source packs. It does not fetch or
publish anything. The public projection is intentionally narrow: change counts,
hashes, and operator-policy allowlisted public metadata only, with no raw
source text or arbitrary local identifiers.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
from typing import Any

from chorus.item import DiscourseItem, normalize
from chorus.receipt import input_digest, verify as verify_digest
from chorus.sentiment import score
from chorus.synthesize import synthesize

SCHEMA = "chorus.source-decision/v1"
PUBLIC_SCHEMA = "chorus.public-source-decision/v1"
METHOD_VERSION = "chorus-source-decision/1"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_DISCOURSE_ROW_KINDS = {"comment", "feed_item", "post", "reply"}


class SourceReadError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        path: str | None = None,
        rows_read: int = 0,
        items_read: int = 0,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.path = path
        self.rows_read = rows_read
        self.items_read = items_read


def _sha(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _text_sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_rows(path: str, *, label: str) -> list[dict]:
    if not path or not os.path.exists(path):
        raise SourceReadError(f"missing_{label}", f"{label} source not found", path=path)
    try:
        if os.path.isdir(path):
            return _load_corpus_dir(path, label=label)
        with open(path, encoding="utf-8") as f:
            rows = json.load(f)
    except json.JSONDecodeError as exc:
        raise SourceReadError(f"invalid_{label}_json", f"{label} source is not valid JSON: {exc}", path=path)
    except OSError as exc:
        raise SourceReadError(f"read_{label}_failed", f"{label} source could not be read: {exc}", path=path)
    if not isinstance(rows, list):
        raise SourceReadError(f"invalid_{label}_shape", f"{label} source JSON must be a list of rows", path=path)
    return rows


def _load_corpus_dir(path: str, *, label: str) -> list[dict]:
    rows = []
    cat = os.path.join(path, "catalog.jsonl")
    if not os.path.exists(cat):
        raise SourceReadError(f"missing_{label}_catalog", f"{label} corpus directory has no catalog.jsonl", path=path)
    rows_read = 0
    items_read = 0
    try:
        with open(cat, encoding="utf-8") as f:
            for line_number, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise SourceReadError(
                        f"invalid_{label}_jsonl",
                        f"{label} catalog.jsonl line {line_number} is not valid JSON: {exc}",
                        path=cat,
                        rows_read=rows_read,
                        items_read=items_read,
                    )
                rows_read += 1
                if row.get("kind") in _DISCOURSE_ROW_KINDS:
                    items_read += 1
                    sha = row.get("sha256")
                    if isinstance(sha, str) and sha:
                        if not _SHA256.fullmatch(sha):
                            raise SourceReadError(
                                f"invalid_{label}_object_hash",
                                f"{label} catalog.jsonl line {line_number} has an invalid sha256",
                                path=cat,
                                rows_read=rows_read,
                                items_read=items_read,
                            )
                        obj = os.path.join(path, "objects", sha[:2], sha[2:])
                        if not os.path.exists(obj):
                            raise SourceReadError(
                                f"missing_{label}_object",
                                f"{label} content object for catalog line {line_number} is missing",
                                path=obj,
                                rows_read=rows_read,
                                items_read=items_read,
                            )
                        with open(obj, "rb") as of:
                            raw = of.read()
                        actual = hashlib.sha256(raw).hexdigest()
                        if actual != sha:
                            raise SourceReadError(
                                f"mismatched_{label}_object_hash",
                                f"{label} content object for catalog line {line_number} does not match catalog sha256",
                                path=obj,
                                rows_read=rows_read,
                                items_read=items_read,
                            )
                        try:
                            row["text"] = raw.decode("utf-8")
                        except UnicodeDecodeError as exc:
                            raise SourceReadError(
                                f"invalid_{label}_object_encoding",
                                f"{label} content object for catalog line {line_number} is not UTF-8: {exc}",
                                path=obj,
                                rows_read=rows_read,
                                items_read=items_read,
                            )
                    elif not isinstance(row.get("text"), str) or not row.get("text", "").strip():
                        raise SourceReadError(
                            f"missing_{label}_text",
                            f"{label} catalog.jsonl line {line_number} has no text or content object",
                            path=cat,
                            rows_read=rows_read,
                            items_read=items_read,
                        )
                rows.append(row)
    except OSError as exc:
        raise SourceReadError(
            f"read_{label}_failed",
            f"{label} corpus could not be read: {exc}",
            path=path,
            rows_read=rows_read,
            items_read=items_read,
        )
    return rows


def _public_url(item: DiscourseItem) -> str | None:
    for key in ("source_url", "url", "permalink"):
        value = item.meta.get(key)
        if isinstance(value, str) and value.strip().lower().startswith(("http://", "https://")):
            return value.strip()
    return None


_SAFE_PUBLIC_VALUE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")


def _safe_public_value(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    clean = value.strip()
    if not clean:
        return None
    if "\\" in clean or "/" in clean or ".." in clean or clean.startswith("~"):
        return None
    if re.match(r"^[A-Za-z]:", clean):
        return None
    return clean if _SAFE_PUBLIC_VALUE.fullmatch(clean) else None


def _safe_public_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    clean = value.strip()
    if not clean.lower().startswith(("http://", "https://")):
        return None
    if any(ord(ch) < 32 or ch.isspace() for ch in clean):
        return None
    return clean if len(clean) <= 2048 else None


def _public_policy_info(public_projection_policy: dict | None) -> dict:
    policy = public_projection_policy if isinstance(public_projection_policy, dict) else {}
    return {"provided": bool(policy), "sha256": _sha(policy)}


def _policy_entries(row: dict, public_projection_policy: dict | None) -> list[dict]:
    if not isinstance(public_projection_policy, dict):
        return []
    entries: list[dict] = []
    for section, key in (
        ("items", row.get("id")),
        ("ids", row.get("id")),
        ("text_sha256", row.get("text_sha256")),
        ("item_sha256", row.get("item_sha256")),
    ):
        mapping = public_projection_policy.get(section)
        if not isinstance(mapping, dict) or not isinstance(key, str):
            continue
        entry = mapping.get(key)
        if isinstance(entry, dict):
            entries.append(entry)
    return entries


def _public_metadata(row: dict, public_projection_policy: dict | None) -> dict:
    policy_meta: dict[str, Any] = {}
    for entry in _policy_entries(row, public_projection_policy):
        policy_meta.update(entry)
    out: dict[str, str] = {}
    for public_key in ("id", "source", "responds_to"):
        value = _safe_public_value(policy_meta.get(public_key))
        if value:
            out[public_key] = value
    url = (
        _safe_public_url(policy_meta.get("source_url"))
        or _safe_public_url(policy_meta.get("url"))
        or _safe_public_url(policy_meta.get("permalink"))
    )
    if url:
        out["source_url"] = url
    return out


def _source_ref(item: DiscourseItem) -> dict:
    out = {"id": item.id, "source": item.source, "responds_to": item.responds_to}
    url = _public_url(item)
    if url:
        out["source_url"] = url
    return out


def _fingerprint(item: DiscourseItem) -> dict:
    body = {
        "id": item.id,
        "source": item.source,
        "responds_to": item.responds_to,
        "parent": item.parent,
        "engagement": item.engagement,
        "engagement_present": bool(item.meta.get("engagement_present")),
        "source_url": _public_url(item),
        "text_sha256": _text_sha(item.text),
    }
    body["item_sha256"] = _sha(body)
    return body


def _snapshot(items: list[DiscourseItem], *, label: str) -> tuple[dict[str, dict], list[dict]]:
    by_id: dict[str, dict] = {}
    failures: list[dict] = []
    for item in items:
        if not item.id:
            failures.append({"code": f"missing_{label}_item_id", "message": f"{label} contains an item with no id"})
            continue
        if item.id in by_id:
            failures.append({"code": f"duplicate_{label}_item_id", "message": f"{label} repeats item id {item.id}"})
            continue
        fp = _fingerprint(item)
        fp["ref"] = _source_ref(item)
        by_id[item.id] = fp
    return by_id, failures


def _changed_fields(current: dict, reference: dict) -> list[str]:
    keys = ("source", "responds_to", "parent", "engagement", "engagement_present", "source_url", "text_sha256")
    return [key for key in keys if current.get(key) != reference.get(key)]


def _change_entry(snapshot: dict) -> dict:
    return {
        "id": snapshot["id"],
        "source": snapshot["source"],
        "responds_to": snapshot["responds_to"],
        "source_url": snapshot.get("source_url"),
        "text_sha256": snapshot["text_sha256"],
        "item_sha256": snapshot["item_sha256"],
    }


def _changed_entry(current: dict, reference: dict) -> dict:
    return {
        "id": current["id"],
        "changed_fields": _changed_fields(current, reference),
        "current": _change_entry(current),
        "reference": _change_entry(reference),
    }


def _digest_outline(digest: dict) -> dict:
    return {
        "responds_to": digest["responds_to"],
        "n_items": digest["n_items"],
        "themes": [
            {
                "label": theme["label"],
                "size": theme["size"],
                "item_ids": list(theme["item_ids"]),
                "dissent": theme["dissent"],
                "controversy": theme["controversy"],
            }
            for theme in digest["themes"][:8]
        ],
        "contested": list(digest.get("contested", ())),
        "method": digest["method"],
        "receipt": digest["receipt"],
    }


def _public_ref(row: dict, public_projection_policy: dict | None) -> dict:
    return {
        "public": _public_metadata(row, public_projection_policy),
        "text_sha256": row["text_sha256"],
        "item_sha256": row["item_sha256"],
    }


def _public_receipt(receipt: dict | None) -> dict | None:
    if not receipt:
        return None
    return {
        "method_version": receipt["method_version"],
        "task_sha256": receipt["task_sha256"],
        "current_input_sha256": receipt["current_input_sha256"],
        "reference_input_sha256": receipt["reference_input_sha256"],
        "current_fingerprint_sha256": receipt["current_fingerprint_sha256"],
        "reference_fingerprint_sha256": receipt["reference_fingerprint_sha256"],
        "status": receipt["status"],
        "decision_sha256": receipt["decision_sha256"],
    }


def _public_projection(result: dict, public_projection_policy: dict | None = None) -> dict:
    changes = result.get("changes", {})
    return {
        "schema": PUBLIC_SCHEMA,
        "task_sha256": _text_sha(result.get("task", "")),
        "status": result["status"],
        "decision": result["decision"],
        "human_summary": result["human_summary"],
        "source_counts": result.get("source_counts", {}),
        "changes": {
            "counts": changes.get("counts", {"added": 0, "removed": 0, "changed": 0, "unchanged": 0}),
            "added": [_public_ref(row, public_projection_policy) for row in changes.get("added", [])],
            "removed": [_public_ref(row, public_projection_policy) for row in changes.get("removed", [])],
            "changed": [
                {
                    "changed_fields": row["changed_fields"],
                    "current": _public_ref(row["current"], public_projection_policy),
                    "reference": _public_ref(row["reference"], public_projection_policy),
                }
                for row in changes.get("changed", [])
            ],
        },
        "checks": result.get("checks", {}),
        "public_projection_policy": result.get("public_projection_policy", _public_policy_info(public_projection_policy)),
        "source_failures": [
            {"code": failure["code"], "message": "Source failure; inspect the local result."}
            for failure in result.get("source_failures", [])
        ],
        "receipt": _public_receipt(result.get("receipt")),
        "limitations": [
            "Public projection excludes raw source text, author names, local paths, private session content, and bulk comments.",
            "MATCH only means the compared source ids and fingerprints matched; it does not prove the source set is complete.",
            "DRIFT identifies source changes for review; it does not decide source meaning or product readiness.",
        ],
    }


def _failure_result(
    task: str,
    failures: list[dict],
    *,
    current_path: str | None = None,
    reference_path: str | None = None,
    public_projection_policy: dict | None = None,
) -> dict:
    result = {
        "schema": SCHEMA,
        "ok": False,
        "task": task,
        "status": "UNVERIFIABLE",
        "decision": "hold_for_source_repair",
        "inputs": {"current": current_path, "reference": reference_path},
        "source_counts": {"current_rows": 0, "reference_rows": 0, "current_items": 0, "reference_items": 0},
        "changes": {"counts": {"added": 0, "removed": 0, "changed": 0, "unchanged": 0},
                    "added": [], "removed": [], "changed": []},
        "checks": {"current_digest_verified": False, "reference_digest_verified": False},
        "source_failures": failures,
        "human_summary": "Source comparison is unverifiable; repair the listed source failure before using it.",
        "receipt": None,
        "public_projection_policy": _public_policy_info(public_projection_policy),
    }
    result["public_projection"] = _public_projection(result, public_projection_policy)
    return result


def _count_discourse_rows(rows: list[dict]) -> int:
    return sum(1 for row in rows if isinstance(row, dict) and row.get("kind") in _DISCOURSE_ROW_KINDS)


def _validate_source_rows(rows: list[dict], *, label: str) -> list[dict]:
    failures: list[dict] = []
    for row_number, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            failures.append({
                "code": f"invalid_{label}_row",
                "message": f"{label} row {row_number} is not an object",
            })
            continue
        if row.get("kind") not in _DISCOURSE_ROW_KINDS:
            continue
        item_id = row.get("id")
        if item_id is None:
            failures.append({
                "code": f"missing_{label}_item_id",
                "message": f"{label} row {row_number} has no id",
            })
        elif not isinstance(item_id, str):
            failures.append({
                "code": f"invalid_{label}_item_id",
                "message": f"{label} row {row_number} id is not a string",
            })
        elif not item_id.strip():
            failures.append({
                "code": f"missing_{label}_item_id",
                "message": f"{label} row {row_number} has empty id",
            })
        text = row.get("text")
        if text is None:
            failures.append({
                "code": f"missing_{label}_text",
                "message": f"{label} row {row_number} has no text",
            })
        elif not isinstance(text, str):
            failures.append({
                "code": f"invalid_{label}_text",
                "message": f"{label} row {row_number} text is not a string",
            })
        elif not text.strip():
            failures.append({
                "code": f"missing_{label}_text",
                "message": f"{label} row {row_number} has empty text",
            })
    return failures


def build_decision(
    current_rows: list[dict],
    reference_rows: list[dict],
    *,
    task: str = "",
    public_projection_policy: dict | None = None,
) -> dict:
    failures: list[dict] = []
    if not isinstance(current_rows, list):
        failures.append({"code": "invalid_current_shape", "message": "current source must be a list of rows"})
    if not isinstance(reference_rows, list):
        failures.append({"code": "invalid_reference_shape", "message": "reference source must be a list of rows"})
    if failures:
        return _failure_result(task, failures, public_projection_policy=public_projection_policy)

    failures.extend(_validate_source_rows(current_rows, label="current"))
    failures.extend(_validate_source_rows(reference_rows, label="reference"))
    if failures:
        result = _failure_result(task, failures, public_projection_policy=public_projection_policy)
        result["source_counts"] = {
            "current_rows": len(current_rows),
            "reference_rows": len(reference_rows),
            "current_items": _count_discourse_rows(current_rows),
            "reference_items": _count_discourse_rows(reference_rows),
        }
        result["public_projection"] = _public_projection(result, public_projection_policy)
        return result

    current_items = normalize(current_rows)
    reference_items = normalize(reference_rows)
    if not current_items:
        failures.append({"code": "empty_current_discourse", "message": "current source has no discourse rows"})
    if not reference_items:
        failures.append({"code": "empty_reference_discourse", "message": "reference source has no discourse rows"})

    current_snapshot, current_failures = _snapshot(current_items, label="current")
    reference_snapshot, reference_failures = _snapshot(reference_items, label="reference")
    failures.extend(current_failures)
    failures.extend(reference_failures)
    if failures:
        result = _failure_result(task, failures, public_projection_policy=public_projection_policy)
        result["source_counts"] = {
            "current_rows": len(current_rows),
            "reference_rows": len(reference_rows),
            "current_items": len(current_items),
            "reference_items": len(reference_items),
        }
        result["public_projection"] = _public_projection(result, public_projection_policy)
        return result

    current_scored = score(current_items)
    reference_scored = score(reference_items)
    current_digest = synthesize(current_scored)
    reference_digest = synthesize(reference_scored)
    current_digest_dict = dataclasses.asdict(current_digest)
    reference_digest_dict = dataclasses.asdict(reference_digest)

    current_ids = set(current_snapshot)
    reference_ids = set(reference_snapshot)
    added = [_change_entry(current_snapshot[item_id]) for item_id in sorted(current_ids - reference_ids)]
    removed = [_change_entry(reference_snapshot[item_id]) for item_id in sorted(reference_ids - current_ids)]
    changed = [
        _changed_entry(current_snapshot[item_id], reference_snapshot[item_id])
        for item_id in sorted(current_ids & reference_ids)
        if current_snapshot[item_id]["item_sha256"] != reference_snapshot[item_id]["item_sha256"]
    ]
    unchanged = sorted(
        item_id for item_id in current_ids & reference_ids
        if current_snapshot[item_id]["item_sha256"] == reference_snapshot[item_id]["item_sha256"]
    )
    status = "DRIFT" if added or removed or changed else "MATCH"
    decision = "review_current_sources" if status == "DRIFT" else "source_set_unchanged"
    changes = {
        "counts": {
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
            "unchanged": len(unchanged),
        },
        "added": added,
        "removed": removed,
        "changed": changed,
    }
    receipt_body = {
        "method_version": METHOD_VERSION,
        "task_sha256": _text_sha(task),
        "current_input_sha256": input_digest(current_scored),
        "reference_input_sha256": input_digest(reference_scored),
        "current_fingerprint_sha256": _sha(current_snapshot),
        "reference_fingerprint_sha256": _sha(reference_snapshot),
        "changes": changes,
        "status": status,
    }
    receipt = {**receipt_body, "decision_sha256": _sha(receipt_body)}
    result = {
        "schema": SCHEMA,
        "ok": True,
        "task": task,
        "status": status,
        "decision": decision,
        "inputs": {},
        "source_counts": {
            "current_rows": len(current_rows),
            "reference_rows": len(reference_rows),
            "current_items": len(current_items),
            "reference_items": len(reference_items),
            "comparable_ids": len(current_ids | reference_ids),
        },
        "changes": changes,
        "checks": {
            "current_digest_verified": verify_digest(current_digest, current_scored),
            "reference_digest_verified": verify_digest(reference_digest, reference_scored),
            "current_input_sha256": input_digest(current_scored),
            "reference_input_sha256": input_digest(reference_scored),
        },
        "disagreement": {
            "current": _digest_outline(current_digest_dict),
            "reference": _digest_outline(reference_digest_dict),
        },
        "source_failures": [],
        "receipt": receipt,
        "public_projection_policy": _public_policy_info(public_projection_policy),
        "human_summary": (
            f"Source comparison detected {len(added)} added, {len(removed)} removed, "
            f"and {len(changed)} changed item(s) across {len(current_ids | reference_ids)} comparable ids; "
            f"{'review current sources before reusing the prior decision.' if status == 'DRIFT' else 'no source drift was detected.'}"
        ),
    }
    result["public_projection"] = _public_projection(result, public_projection_policy)
    return result


def decision_from_paths(
    current: str,
    reference: str,
    *,
    task: str = "",
    public_projection_policy: dict | None = None,
) -> dict:
    failures: list[dict] = []
    current_rows: list[dict] | None = None
    reference_rows: list[dict] | None = None
    known_counts: dict[str, tuple[int, int]] = {}
    for label, path in (("current", current), ("reference", reference)):
        try:
            rows = _load_rows(path, label=label)
        except SourceReadError as exc:
            failure = {"code": exc.code, "message": exc.message}
            if exc.path:
                failure["path"] = exc.path
            failures.append(failure)
            known_counts[label] = (exc.rows_read, exc.items_read)
            continue
        if label == "current":
            current_rows = rows
        else:
            reference_rows = rows
    if failures:
        result = _failure_result(
            task,
            failures,
            current_path=current,
            reference_path=reference,
            public_projection_policy=public_projection_policy,
        )
        current_items = _count_discourse_rows(current_rows) if isinstance(current_rows, list) else 0
        reference_items = _count_discourse_rows(reference_rows) if isinstance(reference_rows, list) else 0
        result["source_counts"] = {
            "current_rows": len(current_rows) if isinstance(current_rows, list) else known_counts.get("current", (0, 0))[0],
            "reference_rows": (
                len(reference_rows) if isinstance(reference_rows, list) else known_counts.get("reference", (0, 0))[0]
            ),
            "current_items": current_items if isinstance(current_rows, list) else known_counts.get("current", (0, 0))[1],
            "reference_items": (
                reference_items if isinstance(reference_rows, list) else known_counts.get("reference", (0, 0))[1]
            ),
        }
        result["public_projection"] = _public_projection(result, public_projection_policy)
        return result
    assert current_rows is not None and reference_rows is not None
    result = build_decision(
        current_rows,
        reference_rows,
        task=task,
        public_projection_policy=public_projection_policy,
    )
    result["inputs"] = {"current": current, "reference": reference}
    result["public_projection"] = _public_projection(result, public_projection_policy)
    return result
