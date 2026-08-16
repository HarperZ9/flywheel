"""Owner-private forged Plan and completed Plan-run custody."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Callable
from uuid import uuid4

from .evidence_json import canonical_bytes, canonical_sha256, strict_load_json
from .journey_lock import ExclusiveJourneyLock, JourneyLockBusy, fsync_directory
from .operation_grants import (_parse_time, _secure_owner_only, _utc_text,
                               _validate_owner_ref)
from .plan_run_contract import (FORGE_SCHEMA, PLAN_RUN_REF, PRP_REF, ForgeRecord,
    PlanRunBinding, PlanRunContractError, VerifiedPlanRun,
    parse_plan_run_binding, validate_prp, verify_plan_result)


class PlanRunStoreError(RuntimeError):
    """Fixed durable-storage or replay failure."""

    def __init__(self, code: str = "STORE_COMMIT_FAILED") -> None:
        self.code = code
        super().__init__(code)


def _owner_dir(state_root: Path, family: str, owner_ref: str,
               *, create: bool) -> Path:
    _validate_owner_ref(owner_ref)
    root = Path(state_root) / family
    owner = root / owner_ref
    if create:
        Path(state_root).mkdir(parents=True, exist_ok=True)
        _secure_owner_only(Path(state_root), directory=True)
        root.mkdir(exist_ok=True)
        _secure_owner_only(root, directory=True)
        owner.mkdir(exist_ok=True)
        _secure_owner_only(owner, directory=True)
    return owner


def _path(owner_dir: Path, ref: str, pattern) -> Path:
    if type(ref) is not str or pattern.fullmatch(ref) is None:
        raise ValueError("reference is invalid")
    return owner_dir / f"{canonical_sha256(ref)}.json"


def _sync(path: Path, state_root: Path) -> None:
    with path.open("r+b") as stream:
        os.fsync(stream.fileno())
    for directory in (path.parent, path.parent.parent, Path(state_root)):
        fsync_directory(directory)


def _replace(path: Path, value: dict, state_root: Path) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            _secure_owner_only(temporary, directory=False)
            stream.write(canonical_bytes(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _secure_owner_only(path, directory=False)
        _sync(path, state_root)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _record(value: object, owner_ref: str) -> ForgeRecord:
    try:
        fields = {"schema", "owner_ref", "prp_id", "prp", "prp_sha256",
                  "prompt_sha256", "gates_sha256", "created_at", "seal_sha256"}
        if type(value) is not dict or set(value) != fields:
            raise ValueError
        prp = validate_prp(value["prp"])
        unsigned = {key: item for key, item in value.items()
                    if key != "seal_sha256"}
        if (value["schema"] != FORGE_SCHEMA or value["owner_ref"] != owner_ref
                or PRP_REF.fullmatch(value["prp_id"]) is None
                or value["prp_sha256"] != canonical_sha256(prp)
                or value["prompt_sha256"] != hashlib.sha256(
                    prp["prompt"].encode("utf-8")).hexdigest()
                or value["gates_sha256"] != canonical_sha256(
                    prp["validation_gates"])
                or _utc_text(_parse_time(value["created_at"])) != value["created_at"]
                or value["seal_sha256"] != canonical_sha256(unsigned)):
            raise ValueError
        expected = "fpr_" + canonical_sha256({
            "owner_ref": owner_ref,
            "prp_sha256": value["prp_sha256"]})[:32]
        if value["prp_id"] != expected:
            raise ValueError
        return ForgeRecord(owner_ref, value["prp_id"], prp,
            value["prp_sha256"], value["prompt_sha256"],
            value["gates_sha256"], value["created_at"], value["seal_sha256"])
    except (KeyError, TypeError, ValueError, PlanRunContractError):
        raise PlanRunContractError("PLAN_BINDING_DRIFT") from None


def _binding(record: ForgeRecord) -> PlanRunBinding:
    prp = record.prp
    value = {"schema": "flywheel.plan-run-binding/v1",
        "prp_id": record.prp_id, "prp": prp,
        "prp_sha256": record.prp_sha256, "prompt": prp["prompt"],
        "prompt_sha256": record.prompt_sha256,
        "gates": prp["validation_gates"],
        "gates_sha256": record.gates_sha256,
        "seal_sha256": record.seal_sha256}
    value["binding_sha256"] = canonical_sha256(value)
    return parse_plan_run_binding(value)


def seal_plan_prp(prp: object, *, owner_ref: str, state_root: Path,
                  clock: Callable[[], str]) -> PlanRunBinding:
    """Create once, or return the first intact owner record for an exact PRP."""
    try:
        validated = validate_prp(prp)
        owner = _owner_dir(state_root, "plan-forge", owner_ref, create=True)
        prp_sha = canonical_sha256(validated)
        ref = "fpr_" + canonical_sha256({
            "owner_ref": owner_ref, "prp_sha256": prp_sha})[:32]
        path = _path(owner, ref, PRP_REF)
        with ExclusiveJourneyLock.acquire(owner / ".lock"):
            if path.exists():
                return _binding(_read_record(path, owner_ref))
            created = _utc_text(_parse_time(clock()))
            value = {"schema": FORGE_SCHEMA, "owner_ref": owner_ref,
                "prp_id": ref, "prp": validated, "prp_sha256": prp_sha,
                "prompt_sha256": hashlib.sha256(
                    validated["prompt"].encode("utf-8")).hexdigest(),
                "gates_sha256": canonical_sha256(
                    validated["validation_gates"]), "created_at": created}
            value["seal_sha256"] = canonical_sha256(value)
            _replace(path, value, state_root)
            return _binding(_record(value, owner_ref))
    except (PlanRunContractError, PlanRunStoreError):
        raise
    except JourneyLockBusy:
        raise PlanRunStoreError("STORE_BUSY") from None
    except (OSError, TypeError, ValueError):
        raise PlanRunStoreError() from None


def _read_record(path: Path, owner_ref: str) -> ForgeRecord:
    if not path.is_file():
        raise PlanRunContractError("PLAN_BINDING_DRIFT")
    try:
        _secure_owner_only(path, directory=False)
        return _record(strict_load_json(path.read_bytes(), max_depth=16), owner_ref)
    except PlanRunContractError:
        raise
    except (OSError, TypeError, ValueError):
        raise PlanRunContractError("PLAN_BINDING_DRIFT") from None


def load_plan_prp(prp_id: str, *, owner_ref: str,
                  state_root: Path) -> ForgeRecord:
    try:
        owner = _owner_dir(state_root, "plan-forge", owner_ref, create=False)
        if not owner.is_dir():
            raise PlanRunContractError("PLAN_BINDING_DRIFT")
        _secure_owner_only(owner.parent, directory=True)
        _secure_owner_only(owner, directory=True)
        return _read_record(_path(owner, prp_id, PRP_REF), owner_ref)
    except PlanRunContractError:
        raise
    except (OSError, TypeError, ValueError):
        raise PlanRunContractError("PLAN_BINDING_DRIFT") from None


def verify_plan_run(binding: object, *, owner_ref: str,
                    state_root: Path) -> VerifiedPlanRun:
    try:
        parsed = parse_plan_run_binding(binding)
        record = load_plan_prp(parsed.prp_id, owner_ref=owner_ref,
                               state_root=state_root)
        if _binding(record) != parsed:
            raise PlanRunContractError("PLAN_BINDING_DRIFT")
        return VerifiedPlanRun(parsed, record)
    except PlanRunContractError as exc:
        if exc.code == "INVALID_REQUEST":
            raise
        raise PlanRunContractError("PLAN_BINDING_DRIFT") from None


def plan_run_lock_path(state_root: Path, owner_ref: str,
                       plan_run_ref: str) -> Path:
    owner = _owner_dir(state_root, "plan-runs", owner_ref, create=True)
    _path(owner, plan_run_ref, PLAN_RUN_REF)
    return owner / f".{canonical_sha256(plan_run_ref)}.lock"


def load_plan_result(plan_run_ref: str, *, owner_ref: str, state_root: Path,
                     verifier=verify_plan_result) -> dict | None:
    try:
        owner = _owner_dir(state_root, "plan-runs", owner_ref, create=False)
        if not owner.is_dir():
            return None
        _secure_owner_only(owner.parent, directory=True)
        _secure_owner_only(owner, directory=True)
        path = _path(owner, plan_run_ref, PLAN_RUN_REF)
        if not path.exists():
            return None
        _secure_owner_only(path, directory=False)
        value = strict_load_json(path.read_bytes(), max_depth=16)
        if verifier(value).get("verdict") != "MATCH":
            raise PlanRunStoreError()
        return value
    except PlanRunStoreError:
        raise
    except (OSError, TypeError, ValueError):
        raise PlanRunStoreError() from None


def commit_plan_result(value: dict, *, owner_ref: str, state_root: Path,
                       verifier=verify_plan_result) -> dict:
    try:
        if verifier(value).get("verdict") != "MATCH":
            raise PlanRunStoreError()
        ref = value.get("plan_run_ref", "")
        owner = _owner_dir(state_root, "plan-runs", owner_ref, create=True)
        path = _path(owner, ref, PLAN_RUN_REF)
        with ExclusiveJourneyLock.acquire(owner / ".lock"):
            prior = load_plan_result(ref, owner_ref=owner_ref,
                                     state_root=state_root, verifier=verifier)
            if prior is not None:
                if prior == value:
                    return prior
                raise PlanRunStoreError("IDEMPOTENCY_MISMATCH")
            _replace(path, value, state_root)
            stored = load_plan_result(ref, owner_ref=owner_ref,
                                      state_root=state_root, verifier=verifier)
            if stored is None:
                raise PlanRunStoreError()
            return stored
    except PlanRunStoreError:
        raise
    except JourneyLockBusy:
        raise PlanRunStoreError("STORE_BUSY") from None
    except (OSError, TypeError, ValueError):
        raise PlanRunStoreError() from None


def persist_forge_seal(run_root, goal: str, *, intent_sha256: str = "",
                       architecture_sha256: str = "") -> str:
    """Preserve the ownerless v1 Studio drift seal; it is never run authority."""
    import time
    body = f"{goal}\x1f{intent_sha256}\x1f{architecture_sha256}"
    prp_id = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
    forge_dir = Path(run_root) / "forge"
    forge_dir.mkdir(parents=True, exist_ok=True)
    (forge_dir / f"{prp_id}.json").write_text(json.dumps({
        "schema": "flywheel.forge-seal/v1", "prp_id": prp_id, "goal": goal,
        "intent_sha256": intent_sha256,
        "architecture_sha256": architecture_sha256,
        "sealed_at": time.time()}, sort_keys=True), encoding="utf-8")
    return prp_id


def forge_recheck(run_root, prp_id: str, req: dict) -> dict:
    """Preserve the v1 Studio Y-arm check and mark it non-authoritative."""
    pid = str(prp_id or "").strip().lower()
    if len(pid) != 16 or any(char not in "0123456789abcdef" for char in pid):
        return {"error": "provide 'prp_id' (16 hex) from the forge response; sealed hashes are read from the server-side seal"}
    path = Path(run_root) / "forge" / f"{pid}.json"
    if not path.is_file():
        return {"error": f"no forge seal on record for prp_id {pid!r}; a recheck needs the seal minted at forge time"}
    seal = json.loads(path.read_text(encoding="utf-8"))
    out = {"schema": "flywheel.prp-recheck/v2", "prp_id": pid,
           "seal_path": str(path), "run_authority": False, "arms": {}}
    for arm in ("intent", "architecture"):
        sealed, current = str(seal.get(f"{arm}_sha256", "")), req.get(f"{arm}_source")
        if not sealed or current is None:
            continue
        if not str(current).strip():
            return {"error": f"empty {arm}_source: an empty arm cannot be drift-checked (empty-vs-empty is moved:false for an arm that never existed)"}
        now = hashlib.sha256(str(current).encode()).hexdigest()
        out["arms"][arm] = {"sealed_sha256": sealed,
                            "current_sha256": now, "moved": now != sealed}
    if not out["arms"]:
        return {"error": "no comparable arm: supply <arm>_source for an arm the seal actually recorded"}
    hashes = [arm["current_sha256"] for arm in out["arms"].values()]
    if len(hashes) == 2 and hashes[0] == hashes[1]:
        out.update({"degenerate": True, "note": "degenerate Y-chain: both arms carry identical content, so the two-arm drift comparison decides nothing; no any_moved verdict is reported"})
        return out
    out["any_moved"] = any(arm["moved"] for arm in out["arms"].values())
    out["note"] = "the Y-chain drift check against the server-held seal: an arm whose current text no longer hashes to the value sealed at forge time moved after the forge"
    return out
