"""Prospective, local-only campaign inputs; no endpoint I/O during preflight."""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import subprocess

from .bulletin_model_campaign import slot_plan
from .bulletin_model_worker import _validate
from .evidence_json import canonical_bytes, strict_load_json
from .private_artifact_fs import open_artifact_root

PATH_FIELDS = {"node", "python", "dart", "flutter_snapshot", "flutter_packages",
               "bulletin_source", "bulletin_dependencies"}
FILE_FIELDS = PATH_FIELDS - {"bulletin_source", "bulletin_dependencies"}


class ManifestError(ValueError):
    pass


def _need(condition):
    if not condition:
        raise ManifestError("campaign_manifest_invalid")


def validate_manifest(value):
    _need(type(value) is dict and set(value) == {"schema", "run_id", "source_commit",
        "bulletin_source_commit", "preregistration_sha256", "amendment_sha256", "profile",
        "paths", "runtime_sha256", "slots", "execution_admitted"})
    _need(value["schema"] == "flywheel.bulletin-model-manifest/v1")
    _need(type(value["execution_admitted"]) is bool)
    _need(type(value["run_id"]) is str and bool(re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", value["run_id"])))
    for key, count in (("source_commit", 40), ("bulletin_source_commit", 40),
                       ("preregistration_sha256", 64), ("amendment_sha256", 64)):
        _need(type(value[key]) is str and bool(re.fullmatch("[a-f0-9]{" + str(count) + "}", value[key])))
    _need(type(value["paths"]) is dict and set(value["paths"]) == PATH_FIELDS)
    _need(type(value["runtime_sha256"]) is dict and set(value["runtime_sha256"]) == FILE_FIELDS)
    for key, raw in value["paths"].items():
        _need(type(raw) is str and Path(raw).is_absolute() and not raw.startswith("\\\\"))
        if key in FILE_FIELDS:
            _need(type(value["runtime_sha256"][key]) is str and bool(re.fullmatch(
                r"[a-f0-9]{64}", value["runtime_sha256"][key])))
    _need(type(value["slots"]) is list and len(value["slots"]) == 12)
    tasks = set()
    for planned, slot in zip(slot_plan(), value["slots"]):
        required = {"slot_id", "condition", "seed", "task_id", "room", "source_payload"}
        _need(type(slot) is dict and set(slot) == required | ({"decoy_payload"} if planned["condition"] == "H3" else set()))
        _need(all(type(slot[k]) is type(v) and slot[k] == v for k, v in planned.items()))
        for field in ("task_id", "room"):
            _need(type(slot[field]) is str and bool(re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", slot[field])))
        _need(slot["room"] == "scratch")  # Existing seeded test room; each slot has a fresh Worker.
        _need(slot["task_id"] not in tasks)
        tasks.add(slot["task_id"])
        payload = slot["source_payload"]
        _need(type(payload) is dict and set(payload) == {"task_id", "state"} |
              ({"note"} if planned["condition"] == "H2" else set()))
        _need(payload["task_id"] == slot["task_id"] and payload["state"] == "reported")
        if planned["condition"] == "H2":
            _need(type(payload["note"]) is str and 0 < len(payload["note"]) < 3000)
        if "decoy_payload" in slot:
            decoy = slot["decoy_payload"]
            _need(type(decoy) is dict and set(decoy) == {"task_id", "state"} and decoy["state"] == "reported"
                  and type(decoy["task_id"]) is str and bool(re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", decoy["task_id"]))
                  and decoy["task_id"] != slot["task_id"])
        _need(len(canonical_bytes(payload)) <= 4000)
    request = {"schema_version": 1, "run_id": value["run_id"], "reservation_id": value["run_id"] + "-readiness",
        "stage_id": "readiness", "profile": value["profile"], "system": "", "messages": [{"role": "user", "content": "OK"}],
        "seed": 0, "temperature": 0, "max_tokens": 32, "timeout_seconds": 60}
    proof = {"schema": "flywheel.bulletin-model-ledger/v1", "kind": "generation_reserved", "ordinal": 1,
             **{k: request[k] for k in ("run_id", "reservation_id", "stage_id", "max_tokens")}}
    _validate(request, proof)  # Existing route/profile validation, no transport creation or calls.
    return strict_load_json(canonical_bytes(value), max_bytes=65536, max_depth=16)


def read_manifest(path, expected_sha256):
    with open_artifact_root(path.parent) as root:
        raw = root.read_bytes(path.name, max_bytes=65536)
    _need(hashlib.sha256(raw).hexdigest() == expected_sha256)
    return validate_manifest(strict_load_json(raw, max_bytes=65536, max_depth=16)), raw


def verify_sources(manifest, repository):
    for repo, expected in ((repository, manifest["source_commit"]),
                           (Path(manifest["paths"]["bulletin_source"]), manifest["bulletin_source_commit"])):
        with open_artifact_root(repo):
            def git(*args):
                return subprocess.run(["git", "-c", "core.fsmonitor=false", "-C", str(repo), *args],
                    capture_output=True, check=True, timeout=15, text=True).stdout.strip()
            _need(git("rev-parse", "HEAD") == expected)
            _need(git("status", "--porcelain", "--untracked-files=all") == "")
    for key in FILE_FIELDS:
        path = Path(manifest["paths"][key])
        digest = hashlib.sha256()
        with open_artifact_root(path.parent) as root:
            # Binary runtimes can be large; bounded stat/read under existing file custody.
            data = root.read_bytes(path.name, max_bytes=268435456)
        digest.update(data)
        _need(digest.hexdigest() == manifest["runtime_sha256"][key])
