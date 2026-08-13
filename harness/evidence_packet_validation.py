"""Bounded preflight and semantic recheck for offline journey packets."""
from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path

from .bundle import LIMITS as BUNDLE_LIMITS, SCHEMA as BUNDLE_SCHEMA
from .bundle import safe_relative, verify_bundle
from .evidence_json import canonical_bytes, canonical_sha256, strict_load_json
from .receipt import Receipt
from .verdict import Attribution, Execution, Verdict

SCHEMA = "flywheel.evidence-packet/v1"
CHECK_KEYS = frozenset(("command", "output_hash", "return_code", "execution",
                        "attribution", "verdict", "denominator"))
DNP = (
    "NOT_PROVES_CHECKER_CORRECTNESS: carried checker source can be inspected but its "
    "presence does not prove that it implements the intended predicate.",
    "NOT_PROVES_EVIDENCE_COMPLETENESS: carried artifacts prove what was packed, not "
    "that no relevant evidence was omitted before packing.",
    "NOT_PROVES_LIVE_PROVIDER_STATE: offline recheck makes no provider or network call.")
MAX_JSON, MAX_FILE, MAX_FILES = 1_048_576, 2_097_152, 1024

def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()

def criterion_basis(journey: dict, claim: dict, oracle_id: str) -> dict:
    return {"schema": "flywheel.evidence-check-criterion/v1",
            "journey_id": journey["journey_id"],
            "journey_sha256": canonical_sha256(journey),
            "event_head_sha256": journey["event_head_sha256"],
            "claim_id": claim["claim_id"], "statement": claim["statement"],
            "oracle_id": oracle_id}

def project(journey: dict) -> tuple[dict, dict[str, dict]]:
    from .evidence_journey import project_journey, verify_journey
    result = verify_journey(journey)
    if result.get("verdict") != "PASS":
        raise ValueError("journey is invalid: " + result.get("reason", "unknown"))
    view = project_journey(journey, lens="verify")
    return view, {claim["claim_id"]: claim for claim in view["detail"]["claims"]}

def named_refs(value: object, key: str) -> set[str]:
    out: set[str] = set()
    if type(value) is dict:
        for name, item in value.items():
            if name == key:
                if type(item) is not list or any(type(ref) is not str for ref in item):
                    raise ValueError(f"{key} must be a list of strings")
                out.update(item)
            else:
                out.update(named_refs(item, key))
    elif type(value) is list:
        for item in value:
            out.update(named_refs(item, key))
    return out

def _canonical_command(check: dict, receipt: Receipt, raw: dict[str, str]) -> None:
    command = check.get("command")
    if type(command) is not dict or set(command) != {"args", "targets"}:
        raise ValueError("check command is not closed")
    args, targets = command.get("args"), command.get("targets")
    if type(args) is not list or type(targets) is not list:
        raise ValueError("check command fields must be lists")
    if any(type(item) is not str for item in args + targets):
        raise ValueError("check command fields must be strings")
    if receipt.coverage.get("oracle_type") == "pytest":
        if args[:3] != ["python", "-m", "pytest"] or len(args) < 4:
            raise ValueError("pytest command prefix drift")
        derived = []
        for argument in args[3:]:
            if argument.startswith("-"):
                raise ValueError("pytest options are not canonical targets")
            ref = argument.split("::", 1)[0]
            if safe_relative(ref).as_posix() != ref or ref not in raw:
                raise ValueError("pytest target is unsafe or not carried")
            if ref not in derived:
                derived.append(ref)
        if targets != derived:
            raise ValueError("pytest target list contradicts command")
    elif targets or args != [receipt.coverage.get("oracle_type")]:
        raise ValueError("non-pytest command is not canonical")

def criterion_fact(receipt: Receipt, claim: dict) -> dict:
    check = receipt.coverage.get("check_result")
    if type(check) is not dict or set(check) != CHECK_KEYS:
        raise ValueError("check_result is not closed")
    artifacts = receipt.coverage.get("raw_artifacts")
    if type(artifacts) is not list:
        raise ValueError("receipt raw artifacts must be a list")
    raw = {item.get("ref"): item.get("sha256") for item in artifacts
           if type(item) is dict}
    if len(raw) != len(artifacts):
        raise ValueError("receipt raw artifacts are malformed or duplicated")
    _canonical_command(check, receipt, raw)
    if Verdict(check.get("verdict")) is not receipt.verdict:
        raise ValueError("check verdict contradicts receipt")
    if Attribution(check.get("attribution")) is not receipt.attribution:
        raise ValueError("check attribution contradicts receipt")
    execution = Execution(check.get("execution"))
    if check.get("denominator") != receipt.denominator.to_dict():
        raise ValueError("check denominator contradicts receipt")
    if type(check.get("return_code")) is not int:
        raise ValueError("check return code is not an integer")
    output_hash = check.get("output_hash")
    if (type(output_hash) is not str or len(output_hash) != 16
            or any(char not in "0123456789abcdef" for char in output_hash)):
        raise ValueError("check output hash is malformed")
    if execution is Execution.TIMEOUT:
        if check["return_code"] != 124 or receipt.denominator.timeouts != 1:
            raise ValueError("timeout facts contradict")
    elif receipt.denominator.timeouts:
        raise ValueError("non-timeout execution records a timeout")
    output_ref = receipt.coverage.get("oracle_output_ref")
    if raw.get(output_ref) != receipt.raw_stdout_sha256:
        raise ValueError("oracle output ref drift")
    return {"claim_id": receipt.objective, "statement": claim["statement"],
            "depends_on": claim["depends_on"],
            "criterion_id": receipt.criterion_id,
            "criterion_sha256": receipt.criterion_sha256,
            "verdict": receipt.verdict.value,
            "denominator": receipt.denominator.to_dict(), "check_result": check}

def _prefix(journey: dict, head: object) -> dict | None:
    matches = ([] if head is None else
               [index for index, event in enumerate(journey["events"])
                if event.get("event_sha256") == head])
    if head is not None and not matches:
        return None
    count = 0 if head is None else matches[0] + 1
    prefix = deepcopy(journey)
    prefix["events"] = deepcopy(journey["events"][:count])
    prefix["stage"] = "intake" if not count else prefix["events"][-1]["stage"]
    prefix["event_head_sha256"] = head
    return prefix

def _read_bounded(path: Path, limit: int) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"{path.name} exceeds byte limit")
    return data

def _preflight(root: Path) -> tuple[dict, dict[str, dict]]:
    paths = [path for path in root.rglob("*")
             if path.is_file() or path.is_symlink()]
    if len(paths) > MAX_FILES:
        raise ValueError("packet exceeds file-count limit")
    parsed: dict[str, dict] = {}
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise ValueError("packet contains a symlink")
        is_json = path.suffix.lower() == ".json"
        data = _read_bounded(path, MAX_JSON if is_json else MAX_FILE)
        if is_json:
            rel = path.relative_to(root).as_posix()
            parsed[rel] = strict_load_json(data, max_depth=32)
    manifest = parsed.get("manifest.json")
    if type(manifest) is not dict or type(manifest.get("files")) is not list:
        raise ValueError("manifest is missing or malformed")
    if len(manifest["files"]) > MAX_FILES:
        raise ValueError("manifest exceeds file-count limit")
    rels = []
    for item in manifest["files"]:
        if type(item) is not dict:
            raise ValueError("manifest file entry must be an object")
        rels.append(safe_relative(item.get("path")).as_posix())
    if len(rels) != len(set(rels)):
        raise ValueError("manifest contains duplicate paths")
    return manifest, parsed

def _drift(detail: str) -> dict:
    return {"schema": SCHEMA, "verdict": "DRIFT", "detail": detail}

def _raw_facts(root: Path, criterion: dict, journey: dict) -> dict[str, str]:
    actual: dict[str, str] = {}
    artifacts = criterion.get("raw_artifacts")
    if type(artifacts) is not list:
        raise ValueError("raw evidence facts are missing")
    for index, item in enumerate(artifacts):
        if type(item) is not dict or set(item) != {"ref", "sha256", "bytes", "packet_path"}:
            raise ValueError("raw evidence fact is not closed")
        ref, packet_path = item["ref"], item["packet_path"]
        if safe_relative(ref).as_posix() != ref or ref in actual:
            raise ValueError("raw evidence ref is unsafe or duplicated")
        blob = _read_bounded(root / safe_relative(packet_path), MAX_FILE)
        value = digest(blob)
        expected_path = f"checker/raw/{index:04d}-{value[7:23]}.txt"
        if packet_path != expected_path or item["sha256"] != value or item["bytes"] != len(blob):
            raise ValueError("raw evidence digest, size, or path drift")
        actual[ref] = value
    if list(actual) != sorted(actual) or set(actual) != named_refs(journey, "raw_artifact_refs"):
        raise ValueError("raw evidence refs drift")
    return actual

def verify_journey_packet(packet_dir: Path) -> dict:
    """Preflight all bytes, then recheck packet facts without oracle dispatch."""
    root = Path(packet_dir)
    try:
        manifest, parsed = _preflight(root)
    except (KeyError, OSError, TypeError, ValueError, RecursionError) as exc:
        return {"schema": SCHEMA, "verdict": "UNVERIFIABLE",
                "detail": f"packet preflight failed: {exc}"}
    bundle = verify_bundle(root)
    if bundle.get("verdict") != "MATCH":
        return {"schema": SCHEMA, **bundle}
    try:
        criterion = deepcopy(parsed["criterion.json"])
        claimed = criterion.pop("criterion_sha256", None)
        if criterion.get("schema") != SCHEMA or claimed != canonical_sha256(criterion):
            return _drift("packet criterion drift")
        criterion["criterion_sha256"] = claimed
        journey = criterion["journey"]
        view, claims = project(journey)
        if (criterion.get("journey_sha256") != canonical_sha256(journey)
                or criterion.get("event_head_sha256") != journey["event_head_sha256"]):
            return _drift("journey body or head drift")
        if criterion.get("claim_ids") != view["claim_ids"]:
            return _drift("claim ids drift")
        if (criterion.get("does_not_prove") != list(DNP)
                or manifest.get("does_not_prove") != list(BUNDLE_LIMITS) + list(DNP)):
            return _drift("does_not_prove drift")
        if manifest.get("schema") != BUNDLE_SCHEMA:
            return _drift("manifest schema drift")
        tree = parsed["tree_head.json"]
        expected_tree = {"schema": "flywheel.evidence-journey-head/v1",
                         "size": len(journey["events"]),
                         "root": "sha256:" + str(journey["event_head_sha256"])}
        if tree != expected_tree:
            return _drift("tree head drift")
        raw_actual = _raw_facts(root, criterion, journey)
        expected_criteria, expected_receipts = [], []
        expected_checkers: dict[str, dict] = {}
        seen: set[str] = set()
        receipt_facts = {item.get("claim_sha256"): item
                         for item in criterion.get("receipts", [])
                         if type(item) is dict}
        if len(receipt_facts) != len(criterion.get("receipts", [])):
            return _drift("receipt facts are malformed or duplicated")
        for listed in bundle["receipts"]:
            body = parsed[listed["path"]]["receipt"]
            receipt = Receipt.from_dict(body)
            fact, claim = receipt_facts.get(receipt.claim_sha256()), claims.get(receipt.objective)
            if (fact is None or set(fact) != {"ref", "claim_id", "claim_sha256"}
                    or fact["claim_id"] != receipt.objective or claim is None
                    or fact["ref"] not in claim.get("receipt_refs", [])):
                return _drift("receipt claim binding drift")
            if receipt.verdict.value != claim["verdict"]:
                return _drift("receipt verdict drift")
            if not set(receipt.does_not_prove()).issubset(body.get("does_not_prove", [])):
                return _drift("receipt limits drift")
            expected_criteria.append(criterion_fact(receipt, claim))
            expected_receipts.append({"ref": fact["ref"], "claim_id": receipt.objective,
                                      "claim_sha256": receipt.claim_sha256()})
            for item in receipt.coverage.get("raw_artifacts", []):
                if raw_actual.get(item.get("ref")) != item.get("sha256"):
                    return _drift("receipt raw evidence drift")
            prefix = _prefix(journey, receipt.coverage.get("event_head_sha256"))
            if prefix is None or canonical_sha256(prefix) != receipt.coverage.get("journey_sha256"):
                return _drift("receipt journey prefix drift")
            basis = criterion_basis(prefix, claim, receipt.coverage.get("oracle_id", ""))
            if receipt.criterion_sha256 != digest(canonical_bytes(basis)):
                return _drift("receipt criterion drift")
            name = (f"oracles/{receipt.coverage.get('oracle_type')}-"
                    f"{receipt.checker_source_sha256[7:23]}.py")
            expected_checkers[name] = {"packet_path": "checker/" + name,
                                       "sha256": receipt.checker_source_sha256,
                                       "name": name}
            seen.add(receipt.claim_sha256())
        expected_criteria.sort(key=lambda item: (item["claim_id"], item["criterion_id"]))
        expected_receipts.sort(key=lambda item: item["claim_sha256"])
        if (criterion.get("criteria") != expected_criteria
                or criterion.get("receipts") != expected_receipts):
            return _drift("criterion or receipt facts drift")
        checkers = [expected_checkers[name] for name in sorted(expected_checkers)]
        if criterion.get("checker_manifest") != checkers:
            return _drift("checker manifest drift")
        for item in checkers:
            source = _read_bounded(root / safe_relative(item["packet_path"]), MAX_FILE)
            if digest(source) != item["sha256"]:
                return _drift("checker source drift")
        files = manifest["files"]
        expected_pack = {"schema": BUNDLE_SCHEMA, "receipt_count": len(seen),
                         "raw_artifact_count": len(raw_actual),
                         "checker_count": len(checkers), "file_count": len(files)}
        if criterion.get("pack_manifest") != expected_pack:
            return _drift("pack manifest facts drift")
        names = [item.get("path", "") for item in files]
        if (sum(name.startswith("receipts/") for name in names) != len(seen)
                or sum(name.startswith("checker/raw/") for name in names) != len(raw_actual)
                or sum(name.startswith("checker/oracles/") for name in names) != len(checkers)):
            return _drift("manifest counts drift")
    except (KeyError, OSError, TypeError, ValueError, RecursionError) as exc:
        return _drift(f"packet semantic recheck failed: {exc}")
    return {"schema": SCHEMA, "verdict": "MATCH", "journey_id": journey["journey_id"],
            "event_head_sha256": journey["event_head_sha256"],
            "packet_sha256": digest((root / "manifest.json").read_bytes()),
            "files_checked": bundle["files_checked"], "receipts_checked": len(seen),
            "does_not_prove": criterion["does_not_prove"]}
