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
MAX_JSON, MAX_FILE, MAX_FILES, MAX_DEPTH = 1_048_576, 2_097_152, 1024, 32
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
            else: out.update(named_refs(item, key))
    elif type(value) is list:
        for item in value: out.update(named_refs(item, key))
    return out

def _prefix(journey: dict, head: object) -> dict | None:
    matches = ([] if head is None else
               [index for index, event in enumerate(journey["events"])
                if event.get("event_sha256") == head])
    if head is not None and not matches: return None
    count = 0 if head is None else matches[0] + 1; prefix = deepcopy(journey)
    prefix["events"] = deepcopy(journey["events"][:count])
    prefix["stage"] = "intake" if not count else prefix["events"][-1]["stage"]
    prefix["event_head_sha256"] = head
    return prefix

def _read_bounded(path: Path, limit: int) -> bytes:
    with path.open("rb") as stream: data = stream.read(limit + 1)
    if len(data) > limit: raise ValueError(f"{path.name} exceeds byte limit")
    return data

def _preflight(root: Path) -> tuple[dict, dict[str, dict], dict[str, int]]:
    parsed: dict[str, dict] = {}; disk: dict[str, int] = {}; count = 0
    for path in root.rglob("*"):
        count += 1
        if count > MAX_FILES: raise ValueError("packet exceeds traversal-entry limit")
        rel = path.relative_to(root)
        if len(rel.parts) > MAX_DEPTH: raise ValueError("packet exceeds path-depth limit")
        if path.is_symlink(): raise ValueError("packet contains a symlink")
        if path.is_dir(): continue
        if not path.is_file(): raise ValueError("packet contains a non-file entry")
        name = rel.as_posix(); is_json = path.suffix.lower() == ".json"
        data = _read_bounded(path, MAX_JSON if is_json else MAX_FILE)
        disk[name] = len(data)
        if is_json: parsed[name] = strict_load_json(data, max_depth=MAX_DEPTH)
    manifest = parsed.get("manifest.json")
    if type(manifest) is not dict or type(manifest.get("files")) is not list:
        raise ValueError("manifest is missing or malformed")
    if len(manifest["files"]) > MAX_FILES: raise ValueError("manifest exceeds file-count limit")
    rels = []
    for item in manifest["files"]:
        if type(item) is not dict or set(item) != {"path", "sha256", "bytes"}:
            raise ValueError("manifest file entry is not closed")
        rels.append(safe_relative(item["path"]).as_posix())
    if len(rels) != len(set(rels)): raise ValueError("manifest contains duplicate paths")
    return manifest, parsed, disk

def _denominator(verdict: str, timed_out: bool, filter_hash: str) -> dict:
    return {"attempts": 1, "group_size": 1, "oracle_calls_consumed": 1,
        "hits": int(verdict == "PASS"), "undecided": int(verdict == "UNDECIDED"),
        "unverifiable": int(verdict == "UNVERIFIABLE"), "parse_failures": 0,
        "timeouts": int(timed_out), "tokens_in": 0, "tokens_out": 0,
        "cache_hit_tokens": 0, "tasks_proposed": 0, "tasks_filtered_out": 0,
        "retries": 0, "oracle_feedback_visible": False,
        "filter_id": "evidence-journey.v1", "filter_hash": filter_hash,
        "filter_is_learned": False}

def _command(check: dict, receipt: Receipt, raw: dict[str, dict]) -> None:
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
            if argument.startswith("-"): raise ValueError("pytest option drift")
            ref = argument.split("::", 1)[0]
            if safe_relative(ref).as_posix() != ref or ref not in raw:
                raise ValueError("pytest target is unsafe or not carried")
            if ref not in derived: derived.append(ref)
        if targets != derived: raise ValueError("pytest target list contradicts command")
    elif targets or args != [receipt.coverage.get("oracle_type")]:
        raise ValueError("non-pytest command is not canonical")

def _pytest_result(receipt: Receipt, check: dict, result_blob: bytes,
                   raw: dict[str, dict], filter_hash: str) -> None:
    result = strict_load_json(result_blob, max_depth=8)
    required = {"schema", "command", "inputs", "outcomes", "return_code"}
    if set(result) != required or result["schema"] != "flywheel.pytest-result/v1":
        raise ValueError("pytest result artifact is not closed")
    output_ref = receipt.coverage.get("oracle_output_ref")
    inputs = [item for ref, item in raw.items() if ref != output_ref]
    if result["command"] != check["command"] or result["inputs"] != inputs:
        raise ValueError("pytest result command or inputs drift")
    outcomes, rc = result["outcomes"], result["return_code"]
    if (type(outcomes) is not list or outcomes != sorted(set(outcomes))
            or any(type(item) is not str or not item.endswith(("=PASS", "=FAIL", "=SKIP"))
                   for item in outcomes) or type(rc) is not int):
        raise ValueError("pytest result outcomes or return code are malformed")
    value = hashlib.sha256(("\n".join(outcomes) + f"\n{rc}").encode()).hexdigest()[:16]
    timed_out = rc == 124; verdict = "PASS" if rc == 0 and any(
        item.endswith("=PASS") for item in outcomes) else "FAIL"
    expected = {"command": result["command"], "output_hash": value,
        "return_code": rc, "execution": "TIMEOUT" if timed_out else "COMPLETED",
        "attribution": "CANDIDATE", "verdict": verdict,
        "denominator": _denominator(verdict, timed_out, filter_hash)}
    if check != expected: raise ValueError("check result contradicts carried pytest result")
    if (receipt.verdict.value != verdict or receipt.attribution.value != "CANDIDATE"
            or receipt.denominator.to_dict() != expected["denominator"]):
        raise ValueError("receipt contradicts carried pytest result")

def criterion_fact(receipt: Receipt, claim: dict, result_blob: bytes,
                   journey: dict) -> dict:
    check = receipt.coverage.get("check_result")
    if type(check) is not dict or set(check) != CHECK_KEYS:
        raise ValueError("check_result is not closed")
    artifacts = receipt.coverage.get("raw_artifacts")
    if type(artifacts) is not list: raise ValueError("receipt raw artifacts must be a list")
    raw = {item.get("ref"): item for item in artifacts if type(item) is dict}
    if (len(raw) != len(artifacts) or any(set(item) != {"ref", "sha256", "bytes"}
                                         for item in raw.values())):
        raise ValueError("receipt raw artifacts are malformed or duplicated")
    _command(check, receipt, raw)
    prefix = _prefix(journey, receipt.coverage.get("event_head_sha256"))
    if prefix is None or canonical_sha256(prefix) != receipt.coverage.get("journey_sha256"):
        raise ValueError("receipt journey prefix drift")
    basis = criterion_basis(prefix, claim, receipt.coverage.get("oracle_id", ""))
    filter_hash = digest(canonical_bytes(basis))
    expected_id = f"evidence-journey/{journey['journey_id']}/{claim['claim_id']}"
    if receipt.criterion_id != expected_id or receipt.criterion_sha256 != filter_hash:
        raise ValueError("receipt criterion identity drift")
    candidate_ref = receipt.coverage.get("candidate_ref")
    if candidate_ref not in raw or receipt.candidate_sha256 != raw[candidate_ref]["sha256"]:
        raise ValueError("executed candidate binding drift")
    output_ref = receipt.coverage.get("oracle_output_ref")
    if output_ref not in raw or raw[output_ref]["sha256"] != receipt.raw_stdout_sha256:
        raise ValueError("oracle output ref drift")
    if receipt.coverage.get("oracle_type") == "pytest":
        _pytest_result(receipt, check, result_blob, raw, filter_hash)
    else:
        if (Verdict(check.get("verdict")) is not receipt.verdict
                or Attribution(check.get("attribution")) is not receipt.attribution
                or check.get("denominator") != receipt.denominator.to_dict()
                or type(check.get("return_code")) is not int):
            raise ValueError("generic check result contradicts receipt")
        Execution(check.get("execution"))
    return {"claim_id": receipt.objective, "statement": claim["statement"],
        "depends_on": claim["depends_on"], "criterion_id": receipt.criterion_id,
        "criterion_sha256": receipt.criterion_sha256, "verdict": receipt.verdict.value,
        "denominator": receipt.denominator.to_dict(), "check_result": check}

def _raw_facts(root: Path, criterion: dict, journey: dict) -> dict[str, dict]:
    actual = {}; artifacts = criterion.get("raw_artifacts")
    if type(artifacts) is not list: raise ValueError("raw evidence facts are missing")
    for index, item in enumerate(artifacts):
        if type(item) is not dict or set(item) != {"ref", "sha256", "bytes", "packet_path"}:
            raise ValueError("raw evidence fact is not closed")
        ref, packet_path = item["ref"], item["packet_path"]
        if safe_relative(ref).as_posix() != ref or ref in actual:
            raise ValueError("raw evidence ref is unsafe or duplicated")
        blob = _read_bounded(root / safe_relative(packet_path), MAX_FILE); value = digest(blob)
        expected_path = f"checker/raw/{index:04d}-{value[7:23]}.txt"
        if packet_path != expected_path or item["sha256"] != value or item["bytes"] != len(blob):
            raise ValueError("raw evidence digest, size, or path drift")
        actual[ref] = {"ref": ref, "sha256": value, "bytes": len(blob), "blob": blob,
                       "packet_path": packet_path}
    if list(actual) != sorted(actual) or set(actual) != named_refs(journey, "raw_artifact_refs"):
        raise ValueError("raw evidence refs drift")
    return actual

def _drift(detail: str) -> dict:
    return {"schema": SCHEMA, "verdict": "DRIFT", "detail": detail}

def verify_journey_packet(packet_dir: Path) -> dict:
    """Preflight all bytes, then recheck packet facts without oracle dispatch."""
    root = Path(packet_dir)
    try: manifest, parsed, disk = _preflight(root)
    except (KeyError, OSError, TypeError, ValueError, RecursionError) as exc:
        return {"schema": SCHEMA, "verdict": "UNVERIFIABLE",
                "detail": f"packet preflight failed: {exc}"}
    bundle = verify_bundle(root)
    if bundle.get("verdict") != "MATCH": return {"schema": SCHEMA, **bundle}
    try:
        criterion = deepcopy(parsed["criterion.json"]); claimed = criterion.pop("criterion_sha256", None)
        if criterion.get("schema") != SCHEMA or claimed != canonical_sha256(criterion):
            return _drift("packet criterion drift")
        criterion["criterion_sha256"] = claimed; journey = criterion["journey"]
        view, claims = project(journey)
        if (criterion.get("journey_sha256") != canonical_sha256(journey)
                or criterion.get("event_head_sha256") != journey["event_head_sha256"]):
            return _drift("journey body or head drift")
        if criterion.get("claim_ids") != view["claim_ids"]: return _drift("claim ids drift")
        if (criterion.get("does_not_prove") != list(DNP)
                or manifest.get("does_not_prove") != list(BUNDLE_LIMITS) + list(DNP)):
            return _drift("does_not_prove drift")
        if manifest.get("schema") != BUNDLE_SCHEMA: return _drift("manifest schema drift")
        expected_tree = {"schema": "flywheel.evidence-journey-head/v1",
            "size": len(journey["events"]), "root": "sha256:" + str(journey["event_head_sha256"])}
        if parsed["tree_head.json"] != expected_tree: return _drift("tree head drift")
        raw_actual = _raw_facts(root, criterion, journey)
        expected_criteria, expected_receipts, expected_checkers, seen = [], [], {}, set()
        receipt_facts = {item.get("claim_sha256"): item for item in criterion.get("receipts", [])
                         if type(item) is dict}
        if len(receipt_facts) != len(criterion.get("receipts", [])):
            return _drift("receipt facts are malformed or duplicated")
        for listed in bundle["receipts"]:
            body = parsed[listed["path"]]["receipt"]; receipt = Receipt.from_dict(body)
            fact, claim = receipt_facts.get(receipt.claim_sha256()), claims.get(receipt.objective)
            if (fact is None or set(fact) != {"ref", "claim_id", "claim_sha256"}
                    or fact["claim_id"] != receipt.objective or claim is None
                    or fact["ref"] not in claim.get("receipt_refs", [])):
                return _drift("receipt claim binding drift")
            if receipt.verdict.value != claim["verdict"]: return _drift("receipt verdict drift")
            if not set(receipt.does_not_prove()).issubset(body.get("does_not_prove", [])):
                return _drift("receipt limits drift")
            for item in receipt.coverage.get("raw_artifacts", []):
                actual = raw_actual.get(item.get("ref"))
                if actual is None or item != {key: actual[key] for key in ("ref", "sha256", "bytes")}:
                    return _drift("receipt raw evidence drift")
            output = raw_actual[receipt.coverage["oracle_output_ref"]]["blob"]
            expected_criteria.append(criterion_fact(receipt, claim, output, journey))
            expected_receipts.append({"ref": fact["ref"], "claim_id": receipt.objective,
                                      "claim_sha256": receipt.claim_sha256()})
            name = f"oracles/{receipt.coverage.get('oracle_type')}-{receipt.checker_source_sha256[7:23]}.py"
            expected_checkers[name] = {"packet_path": "checker/" + name,
                                       "sha256": receipt.checker_source_sha256, "name": name}
            seen.add(receipt.claim_sha256())
        expected_criteria.sort(key=lambda item: (item["claim_id"], item["criterion_id"]))
        expected_receipts.sort(key=lambda item: item["claim_sha256"])
        if criterion.get("criteria") != expected_criteria or criterion.get("receipts") != expected_receipts:
            return _drift("criterion or receipt facts drift")
        checkers = [expected_checkers[name] for name in sorted(expected_checkers)]
        if criterion.get("checker_manifest") != checkers: return _drift("checker manifest drift")
        for item in checkers:
            if digest(_read_bounded(root / safe_relative(item["packet_path"]), MAX_FILE)) != item["sha256"]:
                return _drift("checker source drift")
        files = manifest["files"]; names = [item["path"] for item in files]
        expected_paths = {"criterion.json", "qa_card.json", "tree_head.json", "reproduce.py"}
        expected_paths.update(item["path"] for item in bundle["receipts"])
        expected_paths.update(item["packet_path"] for item in criterion["raw_artifacts"])
        expected_paths.update(item["packet_path"] for item in checkers)
        exact_count = len(seen) + len(raw_actual) + len(checkers) + 4
        expected_pack = {"schema": BUNDLE_SCHEMA, "receipt_count": len(seen),
            "raw_artifact_count": len(raw_actual), "checker_count": len(checkers),
            "file_count": exact_count}
        if (criterion.get("pack_manifest") != expected_pack or len(files) != exact_count
                or set(names) != expected_paths or names != sorted(names)
                or set(disk) != expected_paths | {"manifest.json"}
                or any(item["bytes"] != disk.get(item["path"]) for item in files)):
            return _drift("pack manifest facts or exact path set drift")
    except (KeyError, OSError, TypeError, ValueError, RecursionError) as exc:
        return _drift(f"packet semantic recheck failed: {exc}")
    return {"schema": SCHEMA, "verdict": "MATCH", "journey_id": journey["journey_id"],
        "event_head_sha256": journey["event_head_sha256"],
        "packet_sha256": digest(_read_bounded(root / "manifest.json", MAX_JSON)),
        "files_checked": bundle["files_checked"], "receipts_checked": len(seen),
        "does_not_prove": criterion["does_not_prove"]}
