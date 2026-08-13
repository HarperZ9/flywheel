"""Registered-oracle checks and portable, offline evidence-journey packets."""
from __future__ import annotations
from copy import deepcopy
import hashlib, json, os, shlex, subprocess, sys
from pathlib import Path
from .bundle import SCHEMA as BUNDLE_SCHEMA, pack_bundle, safe_relative, verify_bundle
from .evidence_json import admit_artifact_ref, canonical_bytes, canonical_sha256, strict_load_json
from .oracle_registry import default_registry
from .receipt import Receipt
from .receipt_fields import Budget, Denominator, EvidenceKind, Tier
from .receipt_sign import unsigned
from .task import Task
from .verdict import Attribution, Verdict
SCHEMA = "flywheel.evidence-packet/v1"
CHECK_SCHEMA = "flywheel.evidence-check/v1"
_CONTEXT_FIELDS = frozenset(("task_id", "prompt", "oracle_cmd", "candidate_ref",
                             "raw_artifact_refs", "timeout_seconds"))
_DNP = (
    "NOT_PROVES_CHECKER_CORRECTNESS: carried checker source can be inspected but its "
    "presence does not prove that it implements the intended predicate.",
    "NOT_PROVES_EVIDENCE_COMPLETENESS: carried artifacts prove what was packed, not "
    "that no relevant evidence was omitted before packing.",
    "NOT_PROVES_LIVE_PROVIDER_STATE: offline recheck makes no provider or network call.",
)
def _sha(data: bytes) -> str: return "sha256:" + hashlib.sha256(data).hexdigest()
def _unverifiable(reason: str, detail: str, **facts) -> dict:
    return {"schema": CHECK_SCHEMA, "verdict": "UNVERIFIABLE",
            "unverifiable_reason": reason, "reason": detail, **facts}
def _context(value: object) -> dict:
    parsed = strict_load_json(canonical_bytes(value), max_depth=8); unknown = parsed.keys() - _CONTEXT_FIELDS
    if unknown: raise ValueError("unknown context field(s): " + ", ".join(sorted(unknown)))
    for field in ("task_id", "prompt", "oracle_cmd"):
        if type(parsed.get(field)) is not str or not parsed[field].strip(): raise ValueError(f"{field} must be a non-empty string")
    timeout = parsed.get("timeout_seconds", 60); refs = parsed.get("raw_artifact_refs", [])
    if type(timeout) is not int or not 1 <= timeout <= 300: raise ValueError("timeout_seconds must be an integer in [1, 300]")
    if type(refs) is not list or any(type(ref) is not str or not ref for ref in refs): raise ValueError("raw_artifact_refs must be a list of non-empty strings")
    if len(refs) != len(set(refs)): raise ValueError("raw_artifact_refs must not contain duplicates")
    candidate_ref = parsed.get("candidate_ref")
    if candidate_ref is not None and (type(candidate_ref) is not str or not candidate_ref): raise ValueError("candidate_ref must be a non-empty string")
    parsed["timeout_seconds"] = timeout; return parsed
def _pytest_cmd(raw: str, root: Path) -> str:
    try: argv = shlex.split(raw, posix=os.name != "nt")
    except ValueError as exc: raise ValueError("oracle_cmd is malformed") from exc
    if argv: argv[0] = argv[0].strip('"')
    executable = Path(argv[0]).name.lower() if argv else ""
    if (len(argv) < 4 or executable not in {"python", "python.exe", "py", "py.exe"}
            or argv[1:3] != ["-m", "pytest"]):
        raise ValueError("code oracle_cmd must be python -m pytest plus relative tests")
    for arg in argv[3:]:
        if arg.startswith("-"): raise ValueError("pytest options are assigned by the registered oracle")
        admit_artifact_ref(root, arg.split("::", 1)[0])
    safe = [sys.executable, "-m", "pytest", *argv[3:]]; return subprocess.list2cmdline(safe) if os.name == "nt" else shlex.join(safe)
def _oracle_source(oracle) -> tuple[str, bytes]:
    module_name = type(oracle).__module__; source_path = Path(getattr(sys.modules.get(module_name), "__file__", ""))
    if not source_path.is_file() or source_path.suffix != ".py": raise ValueError("registered oracle source is unavailable")
    return module_name, source_path.read_bytes()
def _denominator(verdict: str, timed_out: bool, filter_hash: str) -> Denominator:
    return Denominator(attempts=1, group_size=1, oracle_calls_consumed=1,
        hits=int(verdict == "PASS"), undecided=int(verdict == "UNDECIDED"),
        unverifiable=int(verdict == "UNVERIFIABLE"), parse_failures=0,
        timeouts=int(timed_out), tokens_in=0, tokens_out=0, cache_hit_tokens=0,
        tasks_proposed=0, tasks_filtered_out=0, retries=0,
        oracle_feedback_visible=False, filter_id="evidence-journey.v1",
        filter_hash=filter_hash, filter_is_learned=False)
def _check_basis(journey: dict, claim: dict, oracle_id: str) -> dict:
    return {"schema": "flywheel.evidence-check-criterion/v1", "journey_id": journey["journey_id"],
            "journey_sha256": canonical_sha256(journey),
            "event_head_sha256": journey["event_head_sha256"],
            "claim_id": claim["claim_id"], "statement": claim["statement"],
            "oracle_id": oracle_id}
def run_journey_check(journey: dict, claim_id: str, oracle_id: str,
                      candidate: Path, context: dict) -> dict:
    """Run only a registered oracle and emit a relative-ref, unsigned receipt."""
    from .evidence_journey import project_journey, verify_journey
    checked = verify_journey(journey)
    if checked.get("verdict") != "PASS": return _unverifiable("INVALID_JOURNEY", checked.get("reason", "invalid journey"))
    try:
        ctx = _context(context); view = project_journey(journey, lens="verify")
        claims = {item["claim_id"]: item for item in view["detail"]["claims"]}
        if type(claim_id) is not str or claim_id not in claims: raise ValueError("claim_id does not name an admitted journey claim")
        if type(oracle_id) is not str or not oracle_id.strip(): raise ValueError("oracle_id must be a non-empty string")
    except (TypeError, ValueError, RecursionError) as exc:
        return _unverifiable("INVALID_CONTEXT", str(exc))
    entry = default_registry().entry(oracle_id)
    if entry is None:
        return _unverifiable("ORACLE_UNAVAILABLE", f"no registered oracle for {oracle_id!r}",
            oracle_id=oracle_id, oracle_calls_consumed=0,
            does_not_prove=[f"the {oracle_id!r} claim was not checked"])
    try:
        if not isinstance(candidate, Path): raise ValueError("candidate must be a Path")
        root = candidate.parent.resolve(strict=True); candidate_ref = ctx.get("candidate_ref", candidate.name)
        admitted = admit_artifact_ref(root, candidate_ref)
        if admitted != candidate.resolve(strict=True): raise ValueError("candidate_ref does not identify candidate")
        data = admitted.read_bytes()
        if len(data) > 1_048_576: raise ValueError("candidate exceeds byte limit")
        source = data.decode("utf-8", "strict")
        raw_refs = ctx["raw_artifact_refs"] or [candidate_ref]
        if candidate_ref not in raw_refs: raise ValueError("raw_artifact_refs must include candidate_ref")
        paths = [(ref, admit_artifact_ref(root, ref)) for ref in raw_refs]
        for _, path in paths:
            blob = path.read_bytes()
            if len(blob) > 1_048_576: raise ValueError("raw artifact exceeds byte limit")
            blob.decode("utf-8", "strict")
        cmd = _pytest_cmd(ctx["oracle_cmd"], root) if entry.oracle.oracle_type == "pytest" else ctx["oracle_cmd"]
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        return _unverifiable("MALFORMED_CANDIDATE", str(exc), oracle_id=entry.domain,
                             oracle_calls_consumed=0)
    task = Task(ctx["task_id"], ctx["prompt"], entry.domain, cmd, str(root), candidate_ref)
    if hasattr(entry.oracle, "timeout"): entry.oracle.timeout = ctx["timeout_seconds"]
    try:
        result = entry.oracle.verify(source, task)
        verdict = Verdict(result.verdict()).value
    except Exception as exc:
        return _unverifiable("ORACLE_ERROR", f"registered oracle failed: {type(exc).__name__}",
                             oracle_id=entry.domain, oracle_calls_consumed=1)
    data = admitted.read_bytes(); raw = [{"ref": ref, "sha256": _sha(path.read_bytes()), "bytes": len(path.read_bytes())}
           for ref, path in paths]
    timed_out = result.rc == 124
    execution = "TIMEOUT" if timed_out else result.execution.value; attribution = Attribution.CANDIDATE.value if timed_out else result.attribution.value
    excerpt = result.stdout_excerpt.replace(str(root), "<artifact-root>")
    key = canonical_sha256({"journey_id": journey["journey_id"], "event_head": journey["event_head_sha256"],
                            "claim_id": claim_id, "oracle_id": entry.domain,
                            "candidate_sha256": _sha(data)})[:16]
    output_ref, receipt_ref = f"raw/oracle-{key}.txt", f"receipts/check-{key}.json"
    output_path = admit_artifact_ref(root, output_ref, must_exist=False); output_path.parent.mkdir(parents=True, exist_ok=True); output_path.write_text(excerpt, encoding="utf-8")
    output_blob = output_path.read_bytes(); raw.append({"ref": output_ref, "sha256": _sha(output_blob), "bytes": len(output_blob)})
    basis = _check_basis(journey, claims[claim_id], entry.domain); module_name, checker_source = _oracle_source(entry.oracle)
    denominator = _denominator(verdict, timed_out, _sha(canonical_bytes(basis)))
    receipt = Receipt(criterion_id=f"evidence-journey/{journey['journey_id']}/{claim_id}",
        criterion_version=1, criterion_sha256=_sha(canonical_bytes(basis)),
        family="evidence-journey", family_instance_id=journey["journey_id"],
        generator_id="submitted-candidate", generator_seed=0, candidate_sha256=_sha(data),
        prompt_hash=_sha(ctx["prompt"].encode()), checker_module=module_name, checker_source_sha256=_sha(checker_source),
        executes_candidate_code=entry.oracle.oracle_type == "pytest", oracle_qa_card_hash="", held_out_agreement="NOT_RUN", evidence_kind=EvidenceKind.COMPUTATIONAL,
        tier=Tier.EXECUTION_TEST, verdict=Verdict(verdict), attribution=Attribution(attribution),
        objective=claim_id, incumbent_objective="", incumbent_source="", coverage={**basis, "raw_artifacts": raw, "oracle_type": entry.oracle.oracle_type},
        raw_stdout_sha256=_sha(output_blob), analysis_script_sha256=_sha(checker_source), denominator=denominator, budget=Budget(ctx["timeout_seconds"], 0, 0, timed_out),
        model_ref="submitted", base_weights_digest="", harness_version="evidence-journey/v1",
        unverifiable_reason=result.unverifiable_reason, undecided_reason=result.undecided_reason,
        extra_does_not_prove=entry.does_not_prove)
    envelope, receipt_path = unsigned(receipt), admit_artifact_ref(root, receipt_ref, must_exist=False); receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(envelope, indent=1, sort_keys=True), encoding="utf-8")
    names = ("attempts", "oracle_calls_consumed", "hits", "undecided", "unverifiable", "timeouts")
    return {"schema": CHECK_SCHEMA, "verdict": verdict,
        "reason": result.unverifiable_reason or result.undecided_reason or "",
        "oracle_id": entry.domain, "oracle_type": entry.oracle.oracle_type,
        "execution": execution, "attribution": attribution, "claim_id": claim_id,
        "claim_verdict_before": claims[claim_id]["verdict"], "receipt_ref": receipt_ref,
        "receipt_claim_sha256": receipt.claim_sha256(),
        "raw_artifact_refs": [item["ref"] for item in raw],
        "denominator": {name: getattr(denominator, name) for name in names},
        "does_not_prove": receipt.does_not_prove()}
def _projection(journey: dict) -> tuple[dict, dict[str, dict]]:
    from .evidence_journey import project_journey, verify_journey
    result = verify_journey(journey)
    if result.get("verdict") != "PASS": raise ValueError("journey is invalid: " + result.get("reason", "unknown"))
    view = project_journey(journey, lens="verify"); return view, {claim["claim_id"]: claim for claim in view["detail"]["claims"]}
def _named_refs(value: object, key: str) -> set[str]:
    out: set[str] = set()
    if type(value) is dict:
        for name, item in value.items():
            if name == key:
                if type(item) is not list or any(type(ref) is not str for ref in item): raise ValueError(f"{key} must be a list of strings")
                out.update(item)
            else:
                out.update(_named_refs(item, key))
    elif type(value) is list:
        for item in value:
            out.update(_named_refs(item, key))
    return out
def pack_journey_packet(out_dir: Path, *, journey: dict, artifact_root: Path) -> dict:
    """Pack a journey, its receipts, raw artifacts, and registered checkers."""
    strict_load_json(canonical_bytes(journey), max_depth=64)
    view, claims = _projection(journey); root = Path(artifact_root).resolve(strict=True)
    receipt_refs = sorted(view["receipt_refs"]); raw_refs = sorted(_named_refs(journey, "raw_artifact_refs"))
    if not receipt_refs or not raw_refs: raise ValueError("journey packet requires receipts and raw evidence")
    envelopes, receipt_facts, criteria, checkers = [], [], [], {}
    registry = default_registry()
    for ref in receipt_refs:
        envelope = strict_load_json(admit_artifact_ref(root, ref).read_bytes()); body = envelope.get("receipt")
        receipt = Receipt.from_dict(body); claim = claims.get(receipt.objective)
        if receipt.claim_sha256() != body.get("claim_sha256"): raise ValueError(f"receipt drift: {ref}")
        if claim is None or ref not in claim.get("receipt_refs", []) or receipt.verdict.value != claim["verdict"]:
            raise ValueError(f"receipt {ref} targets no admitted claim or changes its verdict")
        entry = registry.entry(receipt.coverage.get("oracle_id", ""))
        if entry is None or type(entry.oracle).__module__ != receipt.checker_module: raise ValueError(f"receipt {ref} does not name a registered checker")
        module, source = _oracle_source(entry.oracle)
        if _sha(source) != receipt.checker_source_sha256: raise ValueError(f"checker source drift for {module}")
        name = f"oracles/{entry.oracle.oracle_type}-{_sha(source)[7:23]}.py"
        checkers[name] = source.decode("utf-8", "strict"); envelopes.append(envelope)
        receipt_facts.append({"ref": ref, "claim_id": receipt.objective,
                              "claim_sha256": receipt.claim_sha256()})
        criteria.append({"claim_id": receipt.objective, "criterion_id": receipt.criterion_id,
                         "criterion_sha256": receipt.criterion_sha256,
                         "verdict": receipt.verdict.value, "denominator": receipt.denominator.to_dict()})
    raw_facts = []
    for index, ref in enumerate(raw_refs):
        blob = admit_artifact_ref(root, ref).read_bytes()
        try: text = blob.decode("utf-8", "strict")
        except UnicodeError as exc: raise ValueError(f"raw artifact {ref} is not UTF-8 text") from exc
        name = f"raw/{index:04d}-{hashlib.sha256(blob).hexdigest()[:16]}.txt"; checkers[name] = text
        raw_facts.append({"ref": ref, "sha256": _sha(blob), "bytes": len(blob),
                          "packet_path": "checker/" + name})
    actual = {item["ref"]: item["sha256"] for item in raw_facts}
    for envelope in envelopes:
        expected = {item["ref"]: item["sha256"] for item in envelope["receipt"]["coverage"].get("raw_artifacts", [])}
        if not expected or any(actual.get(ref) != digest for ref, digest in expected.items()): raise ValueError("receipt raw evidence is omitted or drifted")
    checker_manifest = [{"packet_path": "checker/" + name, "sha256": _sha(source.encode()), "name": name}
        for name, source in sorted(checkers.items()) if name.startswith("oracles/")]
    criterion = {"schema": SCHEMA, "journey": journey, "journey_sha256": canonical_sha256(journey),
        "event_head_sha256": journey["event_head_sha256"], "claim_ids": view["claim_ids"],
        "criteria": criteria, "receipts": receipt_facts, "raw_artifacts": raw_facts,
        "checker_manifest": checker_manifest,
        "pack_manifest": {"schema": BUNDLE_SCHEMA, "receipt_count": len(envelopes),
                          "raw_artifact_count": len(raw_facts), "checker_count": len(checker_manifest)},
        "does_not_prove": list(_DNP)}
    criterion["criterion_sha256"] = canonical_sha256(criterion); out = Path(out_dir)
    if out.exists() and any(out.iterdir()): raise ValueError("packet output directory must be empty")
    pack_bundle(out, envelopes=envelopes, criterion=criterion, checker_sources=checkers,
        qa_card={"schema": "flywheel.oracle-qa-card/v2", "passed": False,
                 "reason": "no aggregate QA card is asserted by this packet"},
        tree_head={"schema": "flywheel.evidence-journey-head/v1", "size": len(journey["events"]),
                   "root": "sha256:" + str(journey["event_head_sha256"])})
    path = out / "manifest.json"; manifest = strict_load_json(path.read_bytes())
    manifest["does_not_prove"] = list(dict.fromkeys(manifest.get("does_not_prove", []) + list(_DNP)))
    path.write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8")
    return verify_journey_packet(out)
def _drift(detail: str, **facts) -> dict:
    return {"schema": SCHEMA, "verdict": "DRIFT", "detail": detail, **facts}
def _prefix(journey: dict, head: object) -> dict | None:
    if head is None: count = 0
    else:
        matches = [i for i, event in enumerate(journey["events"]) if event.get("event_sha256") == head]
        if not matches: return None
        count = matches[0] + 1
    prefix = deepcopy(journey); prefix["events"] = deepcopy(journey["events"][:count])
    prefix["stage"] = "intake" if not count else prefix["events"][-1]["stage"]; prefix["event_head_sha256"] = head
    return prefix
def verify_journey_packet(packet_dir: Path) -> dict:
    """Offline structural recheck. Never dispatches an oracle or a provider."""
    bundle = verify_bundle(packet_dir)
    if bundle.get("verdict") != "MATCH": return {"schema": SCHEMA, **bundle}
    root = Path(packet_dir)
    try:
        manifest = strict_load_json((root / "manifest.json").read_bytes()); criterion = strict_load_json((root / "criterion.json").read_bytes(), max_depth=64)
        if criterion.get("schema") != SCHEMA: return _drift("criterion is not an evidence packet")
        claimed_hash = criterion.pop("criterion_sha256", None)
        if claimed_hash != canonical_sha256(criterion): return _drift("packet criterion digest drift")
        criterion["criterion_sha256"] = claimed_hash
        if not criterion.get("does_not_prove") or any(item not in manifest.get("does_not_prove", [])
                                                       for item in criterion["does_not_prove"]):
            return _drift("mandatory does_not_prove facts are missing")
        _, claims = _projection(criterion["journey"]); journey = criterion["journey"]
        if (criterion.get("journey_sha256") != canonical_sha256(journey)
                or criterion.get("event_head_sha256") != journey["event_head_sha256"]):
            return _drift("journey body or event head drift")
        raw_actual = {}
        for item in criterion.get("raw_artifacts", []):
            safe_relative(item["ref"]); blob = admit_artifact_ref(root, item["packet_path"]).read_bytes()
            if item.get("sha256") != _sha(blob) or item.get("bytes") != len(blob): return _drift(f"raw evidence drift: {item.get('ref', '')}")
            raw_actual[item["ref"]] = item["sha256"]
        if not raw_actual: return _drift("raw evidence is omitted")
        checker_actual = {}
        for item in criterion.get("checker_manifest", []):
            blob = admit_artifact_ref(root, item["packet_path"]).read_bytes()
            if item.get("sha256") != _sha(blob): return _drift("checker manifest drift")
            checker_actual[item["name"]] = item["sha256"]
        receipt_map = {item["claim_sha256"]: item for item in criterion.get("receipts", [])}
        criteria = {item["claim_id"]: item for item in criterion.get("criteria", [])}; seen = set()
        for listed in bundle["receipts"]:
            body = strict_load_json((root / listed["path"]).read_bytes())["receipt"]
            receipt = Receipt.from_dict(body); fact = receipt_map.get(receipt.claim_sha256())
            claim = claims.get(receipt.objective)
            if fact is None or fact.get("claim_id") != receipt.objective or claim is None or fact.get("ref") not in claim.get("receipt_refs", []): return _drift("receipt is not bound to an admitted claim")
            if receipt.checker_source_sha256 not in checker_actual.values(): return _drift("receipt checker source drift")
            if receipt.verdict.value != claim["verdict"]: return _drift("receipt verdict differs from journey claim")
            if not set(receipt.does_not_prove()).issubset(set(body.get("does_not_prove", []))): return _drift("receipt does_not_prove drift")
            if criteria.get(receipt.objective, {}).get("denominator") != receipt.denominator.to_dict(): return _drift("receipt denominator drift")
            coverage = receipt.coverage
            if any(raw_actual.get(item.get("ref")) != item.get("sha256")
                   for item in coverage.get("raw_artifacts", [])):
                return _drift("receipt raw evidence drift")
            prefix = _prefix(journey, coverage.get("event_head_sha256"))
            if prefix is None or canonical_sha256(prefix) != coverage.get("journey_sha256"): return _drift("receipt journey-prefix drift")
            basis = _check_basis(prefix, claim, coverage.get("oracle_id", ""))
            if receipt.criterion_sha256 != _sha(canonical_bytes(basis)): return _drift("receipt criterion drift")
            seen.add(receipt.claim_sha256())
        if seen != set(receipt_map): return _drift("packet receipt manifest drift")
        facts = criterion.get("pack_manifest", {})
        if (facts.get("schema") != BUNDLE_SCHEMA or facts.get("receipt_count") != len(seen)
                or facts.get("raw_artifact_count") != len(raw_actual)
                or facts.get("checker_count") != len(checker_actual)):
            return _drift("pack manifest facts drift")
    except (KeyError, OSError, TypeError, ValueError, RecursionError) as exc:
        return _drift(f"packet semantic recheck failed: {exc}")
    return {"schema": SCHEMA, "verdict": "MATCH", "journey_id": journey["journey_id"],
            "event_head_sha256": journey["event_head_sha256"],
            "packet_sha256": _sha((root / "manifest.json").read_bytes()),
            "files_checked": bundle["files_checked"], "receipts_checked": len(seen),
            "does_not_prove": criterion["does_not_prove"]}
