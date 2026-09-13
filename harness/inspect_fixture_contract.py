from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .evidence_json import canonical_bytes, canonical_sha256, strict_load_json
from .inspect_evidence import import_inspect_log
from .private_artifact_fs import open_artifact_root, root_identity, supported

FIXTURE_SCHEMA = "flywheel.inspect-contract-fixture/v1"
MANIFEST_SCHEMA = "flywheel.inspect-fixture-manifest/v1"
REPORT_SCHEMA = "flywheel.inspect-fixture-drift-report/v1"
PROJECTION = "DERIVED allowlisted Inspect JSON: version/status/invalidated, eval task/model/config.limit, results counts/scorer coverage, sample id/epoch/status/error/score values only; no prompts, messages, outputs, paths, timestamps, metrics, run IDs, or local metadata."
INSPECT_VERSION = "0.3.263"
INSPECT_SCHEMA_VERSION = 2
MAX_BYTES = 1_048_576
REQUIRED_V1_FIXTURES = {
    "single-success": "single-success.fixture.json", "single-invalidated": "single-invalidated.fixture.json",
    "epochs-success": "epochs-success.fixture.json", "epochs-invalidated": "epochs-invalidated.fixture.json",
}

def fixture_bytes_name(fixture_id: str) -> str:
    if not fixture_id or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for ch in fixture_id):
        raise ValueError("fixture id must be lowercase slug")
    return f"{fixture_id}.fixture.json"


def build_contract_fixture(fixture_id: str, raw: bytes, *, producer_version: str = INSPECT_VERSION) -> dict:
    source = strict_load_json(raw, max_bytes=MAX_BYTES, max_depth=32)
    projected = _project(source)
    fixture = {
        "schema": FIXTURE_SCHEMA,
        "id": fixture_id,
        "kind": "DERIVED",
        "producer": {
            "format": "inspect-json",
            "inspect_ai_version": producer_version,
            "inspect_schema_version": projected.get("version"),
        },
        "projection": {
            "description": PROJECTION,
            "allowlist": [
                "/version", "/status", "/invalidated", "/eval/task", "/eval/model",
                "/eval/config/limit", "/results/total_samples",
                "/results/completed_samples", "/results/scores/*",
                "/samples/*/id", "/samples/*/epoch", "/samples/*/status",
                "/samples/*/error", "/samples/*/scores/*/value",
            ],
        },
        "source": {
            "original_sha256": hashlib.sha256(raw).hexdigest(),
            "original_byte_length": len(raw),
            "projected_sha256": canonical_sha256(projected),
        },
        "inspect_log": projected,
    }
    fixture["fixture_sha256"] = canonical_sha256(fixture)
    return fixture


def build_manifest(entries: list[dict[str, Any]]) -> dict:
    manifest = {"schema": MANIFEST_SCHEMA, "fixtures": []}
    for entry in entries:
        fixture = entry["fixture"]
        manifest["fixtures"].append({
            "id": entry["id"],
            "path": entry["path"],
            "bytes_sha256": hashlib.sha256(entry["bytes"]).hexdigest(),
            "fixture_sha256": fixture["fixture_sha256"],
            "source_original_sha256": fixture["source"]["original_sha256"],
            "producer": dict(fixture["producer"]),
            "expected": entry["expected"],
        })
    manifest["manifest_identity"] = manifest_identity(manifest)
    return manifest


def manifest_identity(manifest: dict) -> str:
    return canonical_sha256({k: v for k, v in manifest.items() if k != "manifest_identity"})


def check_fixture_dir(root: str | Path) -> dict:
    root = Path(root)
    report = {"schema": REPORT_SCHEMA, "status": "ok", "manifest": {"problems": []}, "fixtures": []}
    try:
        manifest_raw = _read_ref(root, "manifest.json")
        manifest = _load(manifest_raw, "manifest")
    except Exception as exc:
        report["manifest"]["problems"].append(_problem("manifest_unreadable", _safe_error(exc)))
        report["status"] = "drift"
        return report
    if manifest.get("schema") != MANIFEST_SCHEMA:
        report["manifest"]["problems"].append(_problem("manifest_schema_mismatch"))
    if type(manifest.get("manifest_identity")) is not str:
        report["manifest"]["problems"].append(_problem("manifest_identity_malformed"))
    elif manifest.get("manifest_identity") != manifest_identity(manifest):
        report["manifest"]["problems"].append(_problem("manifest_identity_mismatch"))
    for entry in _manifest_entries(manifest, report["manifest"]["problems"]):
        report["fixtures"].append(_check_entry(root, entry))
    if report["manifest"]["problems"] or any(item["problems"] for item in report["fixtures"]):
        report["status"] = "drift"
    return report


def _manifest_entries(manifest: dict, problems: list[dict]) -> list[dict]:
    fixtures = manifest.get("fixtures")
    if type(fixtures) is not list:
        problems.append(_problem("manifest_fixtures_malformed"))
        return []
    entries, seen = [], {}
    for index, entry in enumerate(fixtures):
        if type(entry) is not dict:
            problems.append(_problem("manifest_fixture_entry_malformed", str(index)))
            continue
        fixture_id = entry.get("id")
        if type(fixture_id) is not str:
            problems.append(_problem("manifest_fixture_id_malformed", str(index)))
        else:
            seen[fixture_id] = seen.get(fixture_id, 0) + 1
        entries.append(entry)
    for fixture_id, count in seen.items():
        if count > 1:
            problems.append(_problem("manifest_fixture_duplicate", fixture_id))
        if fixture_id not in REQUIRED_V1_FIXTURES:
            problems.append(_problem("manifest_fixture_extra", fixture_id))
    for fixture_id in REQUIRED_V1_FIXTURES:
        if fixture_id not in seen:
            problems.append(_problem("manifest_fixture_missing", fixture_id))
    return entries


def _check_entry(root: Path, entry: dict) -> dict:
    out = {"id": entry.get("id"), "status": "ok", "problems": []}
    if not _check_entry_manifest_fields(entry, out["problems"]):
        out["status"] = "drift"
        return out
    try:
        raw = _read_ref(root, entry.get("path"))
    except Exception as exc:
        out["problems"].append(_problem("fixture_path_rejected", _safe_error(exc)))
        out["status"] = "drift"
        return out
    if hashlib.sha256(raw).hexdigest() != entry.get("bytes_sha256"):
        out["problems"].append(_problem("fixture_bytes_sha256_mismatch"))
    try:
        fixture = _load(raw, "fixture")
    except ValueError as exc:
        out["problems"].append(_problem("fixture_json_invalid", str(exc)))
        out["status"] = "drift"
        return out
    _check_fixture_shape(fixture, entry, out["problems"])
    if not out["problems"] or all(p["kind"] != "fixture_json_invalid" for p in out["problems"]):
        _check_importer(fixture, entry.get("expected", {}), out)
    out["status"] = "drift" if out["problems"] else "ok"
    return out


def _check_entry_manifest_fields(entry: dict, problems: list[dict]) -> bool:
    fixture_id, path = entry.get("id"), entry.get("path")
    ok = True
    if type(fixture_id) is not str:
        problems.append(_problem("manifest_fixture_id_malformed")); ok = False
    elif fixture_id not in REQUIRED_V1_FIXTURES:
        problems.append(_problem("manifest_fixture_extra", fixture_id)); ok = False
    if type(path) is not str:
        problems.append(_problem("manifest_fixture_path_malformed")); ok = False
    elif type(fixture_id) is str and REQUIRED_V1_FIXTURES.get(fixture_id) != path:
        problems.append(_problem("manifest_fixture_path_mismatch")); ok = False
    for field in ("bytes_sha256", "fixture_sha256", "source_original_sha256"):
        if type(entry.get(field)) is not str:
            problems.append(_problem("manifest_fixture_field_malformed", field)); ok = False
    if type(entry.get("producer")) is not dict:
        problems.append(_problem("manifest_producer_malformed")); ok = False
    expected = entry.get("expected")
    if type(expected) is not dict:
        problems.append(_problem("manifest_expected_malformed")); return False
    counts = expected.get("counts")
    if type(counts) is not dict:
        problems.append(_problem("manifest_expected_counts_malformed")); ok = False
    elif any(k not in counts or type(counts[k]) not in (int, type(None)) for k in ("total_samples", "completed_samples", "observed_samples")):
        problems.append(_problem("manifest_expected_counts_malformed")); ok = False
    if type(expected.get("invalidated")) is not bool:
        problems.append(_problem("manifest_expected_invalidated_malformed")); ok = False
    if type(expected.get("scores")) is not list:
        problems.append(_problem("manifest_expected_scores_malformed")); ok = False
    return ok


def _check_fixture_shape(fixture: dict, entry: dict, problems: list[dict]) -> None:
    if fixture.get("schema") != FIXTURE_SCHEMA: problems.append(_problem("fixture_schema_mismatch"))
    if fixture.get("id") != entry.get("id"): problems.append(_problem("fixture_id_mismatch"))
    if fixture.get("kind") != "DERIVED": problems.append(_problem("fixture_kind_mismatch"))
    if fixture.get("fixture_sha256") != canonical_sha256({k: v for k, v in fixture.items() if k != "fixture_sha256"}):
        problems.append(_problem("fixture_sha256_mismatch"))
    if fixture.get("fixture_sha256") != entry.get("fixture_sha256"): problems.append(_problem("manifest_fixture_sha256_mismatch"))
    source = fixture.get("source", {})
    producer = fixture.get("producer", {})
    log = fixture.get("inspect_log", {})
    if type(source) is not dict:
        problems.append(_problem("fixture_source_malformed")); source = {}
    if type(producer) is not dict:
        problems.append(_problem("fixture_producer_malformed")); producer = {}
    if type(log) is not dict:
        problems.append(_problem("fixture_log_malformed")); log = {}
    if source.get("original_sha256") != entry.get("source_original_sha256"): problems.append(_problem("input_byte_sha256_mismatch"))
    if source.get("projected_sha256") != canonical_sha256(log): problems.append(_problem("projected_sha256_mismatch"))
    if producer != entry.get("producer"): problems.append(_problem("producer_pinning_mismatch"))
    if producer.get("inspect_ai_version") != INSPECT_VERSION: problems.append(_problem("producer_version_mismatch"))
    if producer.get("inspect_schema_version") != INSPECT_SCHEMA_VERSION: problems.append(_problem("producer_schema_version_mismatch"))
    if log.get("version") != INSPECT_SCHEMA_VERSION: problems.append(_problem("inspect_schema_version_mismatch"))


def _check_importer(fixture: dict, expected: dict, out: dict) -> None:
    log = fixture.get("inspect_log", {})
    try:
        imported = import_inspect_log(canonical_bytes(log))
    except ValueError as exc:
        out["problems"].append(_problem("importer_rejected_fixture", type(exc).__name__))
        return
    _check_source_pointers(log, imported, out["problems"])
    out["imported"] = {
        "reported_status": imported["reported_status"],
        "assessment": imported["assessment"],
        "invalidated": imported["invalidated"],
        "semantic_verification": imported["semantic_verification"],
    }
    for key in ("reported_status", "assessment", "invalidated", "semantic_verification"):
        if imported.get(key) != expected.get(key):
            out["problems"].append(_problem("importer_behavior_disagreement", key))
    for key, value in expected.get("counts", {}).items():
        if imported["counts"].get(key) != value:
            out["problems"].append(_problem("importer_count_disagreement", key))
    if _expected_scores(imported) != expected.get("scores", []):
        out["problems"].append(_problem("importer_score_disagreement"))


def _project(source: dict) -> dict:
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


def _project_result_score(item: dict) -> dict:
    return {k: item[k] for k in ("name", "scorer", "scored_samples", "unscored_samples") if k in item}


def _project_sample(sample: dict) -> dict:
    out = {k: sample[k] for k in ("id", "epoch", "status", "error") if k in sample}
    out["scores"] = {name: {"value": score["value"]} for name, score in sample.get("scores", {}).items() if isinstance(score, dict) and "value" in score}
    return out


def _expected_scores(imported: dict) -> list:
    return [{"id": s["id"], "epoch": s["epoch"], "scores": s["scores"]} for s in imported["samples"]]


def _check_source_pointers(source: Any, imported: dict, problems: list[dict]) -> None:
    for ref in imported["source_pointers"]:
        try:
            if _pointer_value(source, ref["json_pointer"]) != ref["source_value"]:
                problems.append(_problem("source_pointer_value_mismatch", ref["json_pointer"]))
        except (KeyError, IndexError, ValueError, TypeError):
            problems.append(_problem("source_pointer_missing", ref["json_pointer"]))


def _pointer_value(value: Any, pointer: str) -> Any:
    for part in pointer.split("/")[1:]:
        key = part.replace("~1", "/").replace("~0", "~")
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def _read_ref(root: Path, ref: object) -> bytes:
    if type(ref) is not str: raise ValueError("fixture reference must be string")
    if not supported(): raise ValueError("safe fixture filesystem unavailable")
    with open_artifact_root(root, expected=root_identity(root), writable=False) as fs:
        return fs.read_bytes(ref, max_bytes=MAX_BYTES)


def _load(raw: bytes, label: str) -> dict:
    try:
        return strict_load_json(raw, max_bytes=MAX_BYTES, max_depth=32)
    except ValueError as exc:
        raise ValueError(f"{label} JSON invalid") from exc


def _problem(kind: str, detail: str = "") -> dict[str, str]:
    return {"kind": kind, "detail": detail} if detail else {"kind": kind}


def _safe_error(exc: BaseException) -> str: return str(getattr(exc, "code", "")) or type(exc).__name__
