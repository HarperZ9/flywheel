"""Bounded offline packets for exact durable Journey-v2 custody."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import stat

from .evidence_json import canonical_bytes, canonical_sha256
from .journey_lock import fsync_directory
from .journey_projection import reduce_events
from .journey_types import PROJECTION_SCHEMA, validate_event

PACKET_SCHEMA = "flywheel.evidence-packet/v1"
PACKET_PROFILE = "flywheel.evidence-journey-custody/v2"
MANIFEST_SCHEMA = "flywheel.evidence-journey-custody-manifest/v1"
TREE_SCHEMA = "flywheel.evidence-journey-custody-tree/v2"
RECEIPT_SCHEMA = "flywheel.evidence-journey-custody-receipt/v1"
MAX_FILE, MAX_FILES, MAX_DEPTH = 1_048_576, 32, 8
PACKET_FILES = (
    "criterion.json", "custody_receipt.json", "events.json",
    "projection.json", "tree_head.json",
)
SOURCE_FILES = ("events.json", "projection.json", "tree_head.json")
DOES_NOT_PROVE = (
    "NOT_PROVES_CLAIM_CORRECTNESS: custody structure does not decide any claim.",
    "NOT_PROVES_EVIDENCE_COMPLETENESS: carried events may omit relevant evidence.",
    "NOT_PROVES_EXECUTION_CONTAINMENT: this packet performs no contained execution.",
    "NOT_PROVES_ORIGIN_AUTHENTICITY: an unsigned packet has no authenticated author.",
    "NOT_PROVES_LIVE_PROVIDER_STATE: offline recheck makes no provider or network call.",
    "NOT_PROVES_DURABLE_FILESYSTEM: recheck does not prove durability outside tested boundaries.",
    "NOT_PROVES_FINAL_EXPORTED_HEAD: the packet binds pre-export H0, not final H1.",
    "NOT_PROVES_CROSS_VERSION_CHECKER_EQUIVALENCE: local checker versions may differ.",
)

def _duplicate_safe(pairs: list[tuple[str, object]]) -> dict:
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value
def _reject_constant(value: str) -> object:
    raise ValueError(f"non-finite JSON number: {value}")
def _depth(value: object) -> int:
    if type(value) is dict:
        return 1 + max((_depth(item) for item in value.values()), default=0)
    if type(value) is list:
        return 1 + max((_depth(item) for item in value), default=0)
    return 0
def _load(data: bytes) -> object:
    if len(data) > MAX_FILE:
        raise ValueError("packet file exceeds byte limit")
    try:
        value = json.loads(data.decode("utf-8", "strict"),
            object_pairs_hook=_duplicate_safe, parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("invalid packet JSON") from exc
    if _depth(value) > MAX_DEPTH:
        raise ValueError("packet JSON exceeds depth limit")
    if _nonfinite(value):
        raise ValueError("non-finite JSON number")
    return value
def _nonfinite(value: object) -> bool:
    if type(value) is float:
        return not math.isfinite(value)
    if type(value) is dict:
        return any(_nonfinite(item) for item in value.values())
    if type(value) is list:
        return any(_nonfinite(item) for item in value)
    return False
def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
def _manifest_digest(data: bytes) -> str:
    return "sha256:" + _digest(data)
def _checker_sha256() -> str:
    return _digest(Path(__file__).read_bytes())
def _safe_ref(value: object) -> str:
    if type(value) is not str or not value or "\\" in value or "\x00" in value:
        raise ValueError("unsafe packet path")
    posix, windows = PurePosixPath(value), PureWindowsPath(value)
    if (value.lower().startswith("file:") or value != posix.as_posix()
            or posix.is_absolute() or windows.is_absolute() or windows.drive
            or ".." in posix.parts or value == "."):
        raise ValueError("unsafe packet path")
    return value
def _reparse(path: Path) -> bool:
    info = path.lstat()
    return path.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & 0x400)
def _write_exclusive(path: Path, value: object) -> None:
    data = canonical_bytes(value)
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
def _inventory(root: Path, names=PACKET_FILES) -> list[dict]:
    return [{"path": name, "sha256": _digest((root / name).read_bytes()),
             "bytes": (root / name).stat().st_size} for name in names]
def _criterion(events: list[dict], projection: dict, tree: dict,
               inventory_sha256: str, checker_source_sha256: str | None = None) -> dict:
    value = {"schema": PACKET_SCHEMA, "profile": PACKET_PROFILE,
        "journey_ref": projection["journey_ref"],
        "source_event_head_sha256": events[-1]["event_sha256"],
        "source_projection_sha256": canonical_sha256(projection),
        "event_count": len(events), "tree_head_sha256": canonical_sha256(tree),
        "inventory_sha256": inventory_sha256,
        "checker_id": "harness.journey_packet_v2",
        "checker_source_sha256": checker_source_sha256 or _checker_sha256(),
        "does_not_prove": list(DOES_NOT_PROVE)}
    value["criterion_sha256"] = canonical_sha256(value)
    return value

def _receipt(criterion: dict) -> dict:
    value = {"schema": RECEIPT_SCHEMA, "profile": PACKET_PROFILE,
        "journey_ref": criterion["journey_ref"],
        "source_event_head_sha256": criterion["source_event_head_sha256"],
        "source_projection_sha256": criterion["source_projection_sha256"],
        "criterion_sha256": criterion["criterion_sha256"],
        "inventory_sha256": criterion["inventory_sha256"],
        "checker_id": criterion["checker_id"],
        "checker_source_sha256": criterion["checker_source_sha256"],
        "structural_verdict": "MATCH", "does_not_prove": list(DOES_NOT_PROVE)}
    value["receipt_sha256"] = canonical_sha256(value)
    return value
def pack_journey_custody_packet(staging_dir: Path, *, events: list[dict],
                                projection: dict) -> dict:
    """Create one exact H0/P0 custody packet and return an offline recheck."""
    checked = [validate_event(event) for event in events]
    reduced = reduce_events(checked)
    if reduced != projection or projection.get("schema") != PROJECTION_SCHEMA:
        raise ValueError("projection does not equal the event-chain reduction")
    out = Path(staging_dir)
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError("packet staging directory must be absent or empty")
    out.mkdir(parents=True, exist_ok=True)
    fsync_directory(out.parent)
    tree = {"schema": TREE_SCHEMA, "journey_ref": projection["journey_ref"],
        "size": len(checked), "root": checked[-1]["event_sha256"],
        "projection_sha256": canonical_sha256(projection)}
    _write_exclusive(out / "events.json", checked)
    _write_exclusive(out / "projection.json", deepcopy(projection))
    _write_exclusive(out / "tree_head.json", tree)
    inventory_sha = canonical_sha256(_inventory(out, SOURCE_FILES))
    criterion = _criterion(checked, projection, tree, inventory_sha)
    _write_exclusive(out / "criterion.json", criterion)
    _write_exclusive(out / "custody_receipt.json", _receipt(criterion))
    files = _inventory(out)
    manifest = {"schema": MANIFEST_SCHEMA, "profile": PACKET_PROFILE,
        "files": files, "inventory_sha256": inventory_sha,
        "does_not_prove": list(DOES_NOT_PROVE)}
    _write_exclusive(out / "manifest.json", manifest)
    fsync_directory(out)
    return verify_journey_custody_packet(out)

def _preflight(root: Path) -> tuple[dict, dict[str, object], dict[str, bytes]]:
    if not root.is_dir() or _reparse(root):
        raise ValueError("packet root is not a regular directory")
    parsed, blobs, entries = {}, {}, 0
    for path in root.rglob("*"):
        entries += 1
        if entries > MAX_FILES or len(path.relative_to(root).parts) > MAX_DEPTH:
            raise ValueError("packet traversal limit exceeded")
        if _reparse(path):
            raise ValueError("packet contains a link or reparse point")
        mode = path.lstat().st_mode
        if stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode):
            raise ValueError("packet contains an irregular file")
        name = path.relative_to(root).as_posix()
        data = path.read_bytes()
        blobs[name] = data
        parsed[name] = _load(data)
    if set(blobs) != set(PACKET_FILES) | {"manifest.json"}:
        raise ValueError("packet exact file set is invalid")
    manifest = parsed["manifest.json"]
    if type(manifest) is not dict:
        raise ValueError("manifest is malformed")
    return manifest, parsed, blobs

def _manifest(manifest: dict, blobs: dict[str, bytes]) -> str | None:
    keys = {"schema", "profile", "files", "inventory_sha256", "does_not_prove"}
    if (set(manifest) != keys or manifest.get("schema") != MANIFEST_SCHEMA
            or manifest.get("profile") != PACKET_PROFILE
            or manifest.get("does_not_prove") != list(DOES_NOT_PROVE)
            or type(manifest.get("files")) is not list):
        raise ValueError("manifest schema or profile is invalid")
    names = []
    for item in manifest["files"]:
        if type(item) is not dict or set(item) != {"path", "sha256", "bytes"}:
            raise ValueError("manifest file entry is invalid")
        name = _safe_ref(item["path"]); names.append(name)
        if (type(item["sha256"]) is not str or len(item["sha256"]) != 64
                or any(char not in "0123456789abcdef" for char in item["sha256"])
                or type(item["bytes"]) is not int or item["bytes"] < 0):
            raise ValueError("manifest digest or size is invalid")
        data = blobs.get(name)
        if data is None or _digest(data) != item["sha256"] or len(data) != item["bytes"]:
            return "packet file digest or size drift"
    if names != list(PACKET_FILES) or len(names) != len(set(names)):
        raise ValueError("manifest inventory is not exact and sorted")
    return None

def _self_hash(value: object, field: str) -> bool:
    if type(value) is not dict or type(value.get(field)) is not str:
        return False
    claimed = value[field]
    return claimed == canonical_sha256({key: item for key, item in value.items()
                                        if key != field})

def _semantic(parsed: dict[str, object], manifest: dict) -> tuple[dict, dict]:
    events, projection = parsed["events.json"], parsed["projection.json"]
    if type(events) is not list or not events or type(projection) is not dict:
        raise ValueError("events or projection is malformed")
    checked = [validate_event(event) for event in events]
    reduced = reduce_events(checked)
    if projection != reduced:
        raise ValueError("projection does not equal the event-chain reduction")
    tree, criterion, receipt = (parsed["tree_head.json"],
        parsed["criterion.json"], parsed["custody_receipt.json"])
    if (type(criterion) is not dict
            or type(criterion.get("checker_source_sha256")) is not str
            or len(criterion["checker_source_sha256"]) != 64
            or any(char not in "0123456789abcdef"
                   for char in criterion["checker_source_sha256"])):
        raise ValueError("checker source identity is malformed")
    expected_tree = {"schema": TREE_SCHEMA, "journey_ref": projection["journey_ref"],
        "size": len(checked), "root": checked[-1]["event_sha256"],
        "projection_sha256": canonical_sha256(projection)}
    source_inventory = [item for item in manifest["files"]
                        if item.get("path") in SOURCE_FILES]
    inventory_sha = canonical_sha256(source_inventory)
    expected_criterion = _criterion(checked, projection, expected_tree,
        inventory_sha, criterion["checker_source_sha256"])
    if (tree != expected_tree or criterion != expected_criterion
            or not _self_hash(criterion, "criterion_sha256")
            or receipt != _receipt(expected_criterion)
            or not _self_hash(receipt, "receipt_sha256")
            or manifest.get("inventory_sha256") != inventory_sha):
        raise ValueError("custody facts drift")
    return projection, criterion

def _failure(verdict: str, detail: str, *, structural: str | None = None) -> dict:
    return {"schema": PACKET_SCHEMA, "profile": PACKET_PROFILE,
        "verdict": verdict, "structural_verdict": structural or verdict,
        "authenticity_verdict": "UNVERIFIABLE",
        "checker_source_verdict": "UNVERIFIABLE",
        "rehash_resistance_verdict": "UNVERIFIABLE", "detail": detail,
        "does_not_prove": list(DOES_NOT_PROVE)}

def verify_journey_custody_packet(packet_dir: Path, *,
        expected_manifest_sha256: str | None = None) -> dict:
    """Recheck exact custody bytes without a store, oracle, registry, or dispatch."""
    root = Path(packet_dir)
    try:
        manifest, parsed, blobs = _preflight(root)
        manifest_blob = blobs["manifest.json"]
        packet_digest = _manifest_digest(manifest_blob)
        if expected_manifest_sha256 is not None:
            valid = (type(expected_manifest_sha256) is str
                and len(expected_manifest_sha256) == 71
                and expected_manifest_sha256.startswith("sha256:")
                and all(char in "0123456789abcdef"
                        for char in expected_manifest_sha256[7:]))
            if not valid:
                return _failure("UNVERIFIABLE", "external anchor is malformed")
            if expected_manifest_sha256 != packet_digest:
                result = _failure("DRIFT", "manifest differs from external anchor")
                result["rehash_resistance_verdict"] = "DRIFT"
                result["packet_digest"] = packet_digest
                return result
        drift = _manifest(manifest, blobs)
        if drift is not None:
            return _failure("DRIFT", drift)
        projection, criterion = _semantic(parsed, manifest)
    except (KeyError, OSError, TypeError, ValueError, RecursionError) as exc:
        detail = str(exc)
        semantic = any(word in detail for word in (
            "projection", "event", "custody", "drift"))
        return _failure("DRIFT" if semantic else "UNVERIFIABLE",
                        "custody recheck failed", structural="DRIFT" if semantic else None)
    anchored = expected_manifest_sha256 is not None
    checker_state = ("MATCH" if criterion["checker_source_sha256"]
                     == _checker_sha256() else "DRIFT")
    return {"schema": PACKET_SCHEMA, "profile": PACKET_PROFILE,
        "verdict": "MATCH" if anchored and checker_state == "MATCH"
                   else "UNVERIFIABLE",
        "structural_verdict": "MATCH", "authenticity_verdict": "UNVERIFIABLE",
        "checker_source_verdict": checker_state,
        "rehash_resistance_verdict": "MATCH" if anchored else "UNVERIFIABLE",
        "authentication": "external-manifest-sha256" if anchored else "unsigned",
        "required_external_anchor": None if anchored else "expected_manifest_sha256",
        "journey_ref": projection["journey_ref"],
        "source_event_head_sha256": criterion["source_event_head_sha256"],
        "source_projection_sha256": criterion["source_projection_sha256"],
        "packet_digest": packet_digest, "files_checked": len(PACKET_FILES),
        "does_not_prove": list(DOES_NOT_PROVE)}
