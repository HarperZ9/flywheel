"""Registered-oracle checks and bounded, offline evidence-journey packets."""
from __future__ import annotations
import hashlib, json, os, shlex, sys, tempfile
from pathlib import Path
from .bundle import LIMITS as BUNDLE_LIMITS, SCHEMA as BUNDLE_SCHEMA, pack_bundle, safe_relative
from .checker_identity import checker_source as _checker_source
from .evidence_json import admit_artifact_ref, canonical_bytes, canonical_sha256, strict_load_json
from .evidence_packet_validation import (DNP as _DNP, MAX_FILE as _MAX_FILE, MAX_JSON as _MAX_JSON,
    SCHEMA, criterion_basis as _basis,
    criterion_fact as _criterion_fact, digest as _sha, named_refs as _named_refs,
    project as _projection, verify_journey_packet)
from .execution_input_protection import ExecutionInputProtectionUnavailable
from .oracle_registry import default_registry
from .receipt import Receipt
from .receipt_fields import Budget, Denominator, EvidenceKind, Tier
from .receipt_sign import unsigned
from .runtime_descriptor import PYTHON_LIMITS
from .task import Task
from .verdict import Attribution, Verdict
CHECK_SCHEMA = "flywheel.evidence-check/v1"
_FIELDS = frozenset(("task_id", "prompt", "oracle_cmd", "candidate_ref",
    "raw_artifact_refs", "timeout_seconds"))
def _unverifiable(code: str, detail: str, **facts) -> dict:
    return {"schema": CHECK_SCHEMA, "verdict": "UNVERIFIABLE",
            "unverifiable_reason": code, "reason": detail, **facts}
def _context(value: object) -> dict:
    parsed = strict_load_json(canonical_bytes(value), max_depth=8)
    unknown = parsed.keys() - _FIELDS
    if unknown:
        raise ValueError("unknown context field(s): " + ", ".join(sorted(unknown)))
    for field in ("task_id", "prompt", "oracle_cmd"):
        if type(parsed.get(field)) is not str or not parsed[field].strip():
            raise ValueError(f"{field} must be a non-empty string")
    timeout, refs, candidate = (parsed.get("timeout_seconds", 60),
        parsed.get("raw_artifact_refs", []), parsed.get("candidate_ref"))
    if type(timeout) is not int or not 1 <= timeout <= 300:
        raise ValueError("timeout_seconds must be an integer in [1, 300]")
    if type(refs) is not list or any(type(ref) is not str or not ref for ref in refs):
        raise ValueError("raw_artifact_refs must be a list of strings")
    if len(refs) != len(set(refs)):
        raise ValueError("raw_artifact_refs must not contain duplicates")
    if candidate is not None and (type(candidate) is not str or not candidate):
        raise ValueError("candidate_ref must be a string")
    parsed["timeout_seconds"] = timeout
    return parsed
def _canonical(root: Path, ref: str) -> tuple[str, Path]:
    path = admit_artifact_ref(root, ref)
    return path.relative_to(root).as_posix(), path
def _read(path: Path, limit: int) -> bytes:
    with path.open("rb") as stream:
        blob = stream.read(limit + 1)
    if len(blob) > limit:
        raise ValueError("input artifact exceeds byte limit")
    return blob
def _snap(root: Path, refs: list[str]) -> dict[str, tuple[bytes, str]]:
    out = {}
    for supplied in refs:
        ref, path = _canonical(root, supplied)
        blob = _read(path, _MAX_JSON)
        if ref in out:
            raise ValueError("artifact refs must be canonically unique")
        blob.decode("utf-8", "strict")
        out[ref] = (blob, _sha(blob))
    return out
def _stable(root: Path, before: dict[str, tuple[bytes, str]]) -> bool:
    try:
        for ref, (blob, claimed) in before.items():
            current = _read(_canonical(root, ref)[1], _MAX_JSON)
            if current != blob or _sha(current) != claimed:
                return False
        return True
    except (OSError, TypeError, ValueError):
        return False
def _pytest_command(raw: str, root: Path, carried: set[str]) -> tuple[list[str], dict]:
    try: argv = shlex.split(raw, posix=os.name != "nt")
    except ValueError as exc: raise ValueError("oracle_cmd is malformed") from exc
    if argv: argv[0] = argv[0].strip('"')
    if (len(argv) < 4 or Path(argv[0]).name.lower() not in {"python", "python.exe", "py", "py.exe"}
            or argv[1:3] != ["-m", "pytest"]):
        raise ValueError("code oracle_cmd must be python -m pytest plus relative targets")
    args, targets = ["python", "-m", "pytest"], []
    for arg in argv[3:]:
        if arg.startswith("-"): raise ValueError("pytest options are assigned by the registered oracle")
        raw_ref, suffix = (arg.split("::", 1) + [""])[:2]; ref, _ = _canonical(root, raw_ref)
        if ref not in carried: raise ValueError(f"pytest target {ref!r} is not carried raw evidence")
        args.append(ref + ("::" + suffix if suffix else "")); targets.append(ref)
    return [sys.executable, "-m", "pytest", *args[3:]], {"args": args, "targets": list(dict.fromkeys(targets))}
def _denominator(verdict: str, timed_out: bool, filter_hash: str) -> Denominator:
    return Denominator(attempts=1, group_size=1, oracle_calls_consumed=1,
        hits=int(verdict == "PASS"), undecided=int(verdict == "UNDECIDED"),
        unverifiable=int(verdict == "UNVERIFIABLE"), parse_failures=0,
        timeouts=int(timed_out), tokens_in=0, tokens_out=0, cache_hit_tokens=0,
        tasks_proposed=0, tasks_filtered_out=0, retries=0,
        oracle_feedback_visible=False, filter_id="evidence-journey.v1",
        filter_hash=filter_hash, filter_is_learned=False)
def run_journey_check(journey: dict, claim_id: str, oracle_id: str, candidate: Path, context: dict) -> dict:
    """Run a registered oracle over snapshotted inputs and emit one receipt."""
    from .evidence_journey import project_journey, verify_journey
    structural = verify_journey(journey)
    if structural.get("verdict") != "PASS":
        return _unverifiable("INVALID_JOURNEY",
                             structural.get("reason", "invalid journey"))
    try:
        ctx = _context(context)
        view = project_journey(journey, lens="verify")
        claims = {claim["claim_id"]: claim for claim in view["detail"]["claims"]}
        if type(claim_id) is not str or claim_id not in claims:
            raise ValueError("claim_id does not name an admitted journey claim")
        if type(oracle_id) is not str or not oracle_id.strip():
            raise ValueError("oracle_id must be a string")
    except (TypeError, ValueError, RecursionError) as exc:
        return _unverifiable("INVALID_CONTEXT", str(exc))
    entry = default_registry().entry(oracle_id)
    if entry is None:
        return _unverifiable("ORACLE_UNAVAILABLE", f"no registered oracle for {oracle_id!r}",
            oracle_id=oracle_id, oracle_calls_consumed=0,
            does_not_prove=[f"the {oracle_id!r} claim was not checked"])
    try:
        if not isinstance(candidate, Path):
            raise ValueError("candidate must be a Path")
        root = candidate.parent.resolve(strict=True)
        candidate_ref, admitted = _canonical(
            root, ctx.get("candidate_ref", candidate.name))
        if admitted != candidate.resolve(strict=True):
            raise ValueError("candidate_ref does not identify candidate")
        supplied = ctx["raw_artifact_refs"] or [candidate_ref]
        before = _snap(root, supplied)
        if candidate_ref not in before:
            raise ValueError("raw_artifact_refs must include candidate_ref")
        if entry.oracle.oracle_type == "pytest":
            oracle_argv, command = _pytest_command(
                ctx["oracle_cmd"], root, set(before))
        else:
            command = {"args": [entry.oracle.oracle_type], "targets": []}
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        return _unverifiable("MALFORMED_CANDIDATE", str(exc), oracle_id=entry.domain, oracle_calls_consumed=0)
    source = before[candidate_ref][0].decode("utf-8", "strict")
    oracle_error = None
    try:
        with tempfile.TemporaryDirectory(prefix="flywheel-evidence-") as temp:
            work = Path(temp) / "input"; work.mkdir()
            for ref, (blob, _) in before.items():
                target = work / safe_relative(ref)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(blob)
            if hasattr(entry.oracle, "timeout"):
                entry.oracle.timeout = ctx["timeout_seconds"]
            execution_before = _snap(work, list(before))
            try:
                if entry.oracle.oracle_type == "pytest":
                    result, artifact, prepared_before = entry.oracle.verify_prepared(
                        oracle_argv, Task(ctx["task_id"], ctx["prompt"], entry.domain,
                            "", str(work), candidate_ref), list(before))
                    if prepared_before != execution_before: raise ValueError("prepared input snapshot drift")
                    output = canonical_bytes(artifact)
                else:
                    task = Task(ctx["task_id"], ctx["prompt"], entry.domain,
                                ctx["oracle_cmd"], str(work), candidate_ref)
                    result = entry.oracle.verify(source, task)
                    excerpt = (result.stdout_excerpt.replace(str(root), "<artifact-root>")
                               .replace(str(work), "<check-root>"))
                    output = excerpt.encode()
            except ExecutionInputProtectionUnavailable as exc:
                return _unverifiable("EXECUTION_INPUT_PROTECTION_UNAVAILABLE", str(exc),
                    oracle_id=entry.domain, oracle_calls_consumed=0)
            except Exception as exc:
                oracle_error, result = exc, None
            stable = _stable(root, before) and _stable(work, execution_before)
    except Exception as exc:
        return _unverifiable("ORACLE_ERROR", f"registered oracle failed: {type(exc).__name__}",
                             oracle_id=entry.domain, oracle_calls_consumed=1)
    if not stable:
        return _unverifiable(
            "INPUT_DRIFT", "an admitted check input changed during oracle execution",
            oracle_id=entry.domain, oracle_calls_consumed=1)
    if oracle_error is not None:
        return _unverifiable("ORACLE_ERROR", f"registered oracle failed: {type(oracle_error).__name__}",
                             oracle_id=entry.domain, oracle_calls_consumed=1)
    verdict, timed_out = Verdict(result.verdict()).value, result.rc == 124
    execution = "TIMEOUT" if timed_out else result.execution.value
    attribution = Attribution.CANDIDATE.value if timed_out else result.attribution.value
    key = canonical_sha256({"journey_id": journey["journey_id"], "event_head": journey["event_head_sha256"],
                            "claim_id": claim_id, "oracle_id": entry.domain,
                            "candidate_sha256": before[candidate_ref][1], "command": command})[:16]
    suffix = "json" if entry.oracle.oracle_type == "pytest" else "txt"
    output_ref, receipt_ref = f"raw/oracle-{key}.{suffix}", f"receipts/check-{key}.json"
    output_path = admit_artifact_ref(root, output_ref, must_exist=False)
    output_path.parent.mkdir(parents=True, exist_ok=True); output_path.write_bytes(output)
    raw = [{"ref": ref, "sha256": claimed, "bytes": len(blob)}
           for ref, (blob, claimed) in before.items()]
    raw.append({"ref": output_ref, "sha256": _sha(output), "bytes": len(output)})
    runtime = artifact["runtime"] if entry.oracle.oracle_type == "pytest" else None
    basis = _basis(journey, claims[claim_id], entry.domain)
    module, checker, runtime_sha = _checker_source(entry.oracle, runtime)
    denominator = _denominator(verdict, timed_out, _sha(canonical_bytes(basis)))
    closed = {"command": command, "output_hash": result.output_hash, "return_code": result.rc,
              "execution": execution, "attribution": attribution, "verdict": verdict,
              "denominator": denominator.to_dict()}
    protection = artifact["execution_input_protection"] if entry.oracle.oracle_type == "pytest" else "not-applicable"
    coverage = {**basis, "oracle_type": entry.oracle.oracle_type,
        "candidate_ref": candidate_ref, "execution_input_protection": protection,
        "raw_artifacts": raw, "oracle_output_ref": output_ref,
        "check_result": closed}
    limits = entry.does_not_prove
    if entry.oracle.oracle_type == "pytest":
        coverage.update(execution_namespace=artifact["execution_namespace"],
            candidate_provenance=artifact["candidate_provenance"],
            dependency_boundary=artifact["dependency_boundary"],
            runtime_descriptor=runtime,
            runtime_descriptor_sha256=runtime_sha)
        limits += PYTHON_LIMITS
    receipt = Receipt(criterion_id=f"evidence-journey/{journey['journey_id']}/{claim_id}",
        criterion_version=1, criterion_sha256=_sha(canonical_bytes(basis)), family="evidence-journey",
        family_instance_id=journey["journey_id"], generator_id="submitted-candidate", generator_seed=0,
        candidate_sha256=before[candidate_ref][1], prompt_hash=_sha(ctx["prompt"].encode()),
        checker_module=module, checker_source_sha256=_sha(checker),
        executes_candidate_code=entry.oracle.oracle_type == "pytest", oracle_qa_card_hash="",
        held_out_agreement="NOT_RUN", evidence_kind=EvidenceKind.COMPUTATIONAL,
        tier=Tier.EXECUTION_TEST, verdict=Verdict(verdict), attribution=Attribution(attribution),
        objective=claim_id, incumbent_objective="", incumbent_source="",
        coverage=coverage,
        raw_stdout_sha256=_sha(output), analysis_script_sha256=_sha(checker), denominator=denominator,
        budget=Budget(ctx["timeout_seconds"], 0, 0, timed_out), model_ref="submitted",
        base_weights_digest="", harness_version="evidence-journey/v1",
        unverifiable_reason=result.unverifiable_reason, undecided_reason=result.undecided_reason,
        extra_does_not_prove=limits)
    path = admit_artifact_ref(root, receipt_ref, must_exist=False); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(unsigned(receipt), indent=1, sort_keys=True), encoding="utf-8")
    names = ("attempts", "oracle_calls_consumed", "hits", "undecided", "unverifiable", "timeouts")
    return {"schema": CHECK_SCHEMA, "verdict": verdict,
        "reason": result.unverifiable_reason or result.undecided_reason or "",
        "oracle_id": entry.domain, "oracle_type": entry.oracle.oracle_type,
        "execution": execution, "attribution": attribution, "claim_id": claim_id,
        "execution_input_protection": protection,
        "candidate_provenance": coverage.get("candidate_provenance"),
        "runtime_descriptor_sha256": runtime_sha,
        "claim_verdict_before": claims[claim_id]["verdict"], "receipt_ref": receipt_ref,
        "receipt_claim_sha256": receipt.claim_sha256(), "raw_artifact_refs": [r["ref"] for r in raw],
        "denominator": {name: getattr(denominator, name) for name in names},
        "check_result": closed, "does_not_prove": receipt.does_not_prove()}
def pack_journey_packet(out_dir: Path, *, journey: dict, artifact_root: Path) -> dict:
    """Pack a journey, receipts, snapshotted raw evidence, and checker sources."""
    strict_load_json(canonical_bytes(journey), max_depth=32); view, claims = _projection(journey)
    root = Path(artifact_root).resolve(strict=True); receipt_refs = sorted(view["receipt_refs"])
    raw_refs = sorted(_named_refs(journey, "raw_artifact_refs"))
    if not receipt_refs or not raw_refs: raise ValueError("journey packet requires receipts and raw evidence")
    envelopes, receipt_facts, criteria, checkers, checker_runtime = [], [], [], {}, {}
    registry = default_registry()
    raw_facts, raw_blobs = [], {}
    for index, ref in enumerate(raw_refs):
        blob = _read(admit_artifact_ref(root, ref), _MAX_FILE); raw_blobs[ref] = blob
        name = f"raw/{index:04d}-{hashlib.sha256(blob).hexdigest()[:16]}.txt"
        checkers[name] = blob.decode("utf-8", "strict")
        raw_facts.append({"ref": ref, "sha256": _sha(blob), "bytes": len(blob),
                          "packet_path": "checker/" + name})
    actual = {item["ref"]: {key: item[key] for key in ("ref", "sha256", "bytes")}
              for item in raw_facts}
    for ref in receipt_refs:
        envelope = strict_load_json(_read(admit_artifact_ref(root, ref), _MAX_JSON))
        body = envelope.get("receipt")
        receipt = Receipt.from_dict(body); claim = claims.get(receipt.objective)
        if receipt.to_dict() != body: raise ValueError(f"receipt wire form drift: {ref}")
        if receipt.claim_sha256() != body.get("claim_sha256"): raise ValueError(f"receipt drift: {ref}")
        if claim is None or ref not in claim.get("receipt_refs", []) or receipt.verdict.value != claim["verdict"]: raise ValueError(f"receipt {ref} changes its claim")
        entry = registry.entry(receipt.coverage.get("oracle_id", ""))
        if entry is None or type(entry.oracle).__module__ != receipt.checker_module: raise ValueError(f"receipt {ref} does not name a registered checker")
        runtime = receipt.coverage.get("runtime_descriptor")
        module, source, runtime_sha = _checker_source(entry.oracle, runtime)
        if _sha(source) != receipt.checker_source_sha256: raise ValueError(f"checker source drift for {module}")
        if runtime_sha != receipt.coverage.get("runtime_descriptor_sha256"):
            raise ValueError(f"checker runtime drift for {module}")
        name = f"oracles/{entry.oracle.oracle_type}-{_sha(source)[7:23]}.json"; checkers[name] = source.decode()
        checker_runtime[name] = runtime_sha
        expected = receipt.coverage.get("raw_artifacts", [])
        if not expected or any(actual.get(item.get("ref")) != item for item in expected):
            raise ValueError("receipt raw evidence is omitted or drifted")
        output_ref = receipt.coverage.get("oracle_output_ref")
        envelopes.append(envelope)
        criteria.append(_criterion_fact(receipt, claim, raw_blobs[output_ref], journey))
        receipt_facts.append({"ref": ref, "claim_id": receipt.objective, "claim_sha256": receipt.claim_sha256()})
    criteria.sort(key=lambda item: (item["claim_id"], item["criterion_id"]))
    receipt_facts.sort(key=lambda item: item["claim_sha256"])
    checker_manifest = [{"packet_path": "checker/" + name, "sha256": _sha(source.encode()),
        "name": name, "runtime_descriptor_sha256": checker_runtime[name]}
        for name, source in sorted(checkers.items()) if name.startswith("oracles/")]
    pack = {"schema": BUNDLE_SCHEMA, "receipt_count": len(envelopes),
            "raw_artifact_count": len(raw_facts), "checker_count": len(checker_manifest),
            "file_count": len(envelopes) + len(checkers) + 4}
    criterion = {"schema": SCHEMA, "journey": journey, "journey_sha256": canonical_sha256(journey),
        "event_head_sha256": journey["event_head_sha256"], "claim_ids": view["claim_ids"],
        "criteria": criteria, "receipts": receipt_facts, "raw_artifacts": raw_facts,
        "checker_manifest": checker_manifest, "pack_manifest": pack, "does_not_prove": list(_DNP)}
    criterion["criterion_sha256"] = canonical_sha256(criterion); out = Path(out_dir)
    if out.exists() and any(out.iterdir()): raise ValueError("packet output directory must be empty")
    pack_bundle(out, envelopes=envelopes, criterion=criterion, checker_sources=checkers,
        qa_card={"schema": "flywheel.oracle-qa-card/v2", "passed": False, "reason": "no aggregate QA card is asserted by this packet"},
        tree_head={"schema": "flywheel.evidence-journey-head/v1", "size": len(journey["events"]), "root": "sha256:" + str(journey["event_head_sha256"])})
    path = out / "manifest.json"; manifest = strict_load_json(path.read_bytes())
    manifest["does_not_prove"] = list(BUNDLE_LIMITS) + list(_DNP); path.write_text(
        json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8"); return verify_journey_packet(out)
