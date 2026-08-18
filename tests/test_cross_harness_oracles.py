import hashlib, json
from pathlib import Path
import pytest
from harness.cross_harness_oracles import OracleContext, evaluate_task_oracle
TASKS = {
    "index_fallback_integrity/v1": "agt-001-index-fallback-integrity",
    "shared_task_artifact/v1": "agt-003-codex-flywheel-shared-task",
    "paired_friction/v1": "agt-009-receipts-vs-guardrails-friction",
    "documentation_maintenance/v1": "agt-010-documentation-schematic-maintenance"}
def _sha(data: bytes) -> str: return hashlib.sha256(data).hexdigest()
def _write(path: Path, value, *, raw=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value if raw else json.dumps(value), encoding="utf-8")
def _sync_output(context, report):
    _write(context.artifact_paths["report.json"], report)
    markdown = context.artifact_paths["report.md"].read_bytes().decode("utf-8")
    _write(context.raw_output_path, {"artifacts": {"report.json": report, "report.md": markdown}})
def _case(tmp_path, checker):
    task_id = TASKS[checker]
    workspace, attempt = tmp_path / "workspace", tmp_path / "attempt"
    input_hashes = {"fixture.json": ""}
    raw, receipt = attempt / "raw.txt", attempt / "receipt.json"
    raw.parent.mkdir(parents=True)
    raw.write_text("raw output", encoding="utf-8"); receipt.write_text("{}", encoding="utf-8")
    core = {"raw_prompt_sha256": "a" * 64, "tool_policy_sha256": "b" * 64,
            "attempt_dir": str(attempt), "workspace_root": str(workspace),
            "raw_artifact_sha256": _sha(raw.read_bytes()), "receipt_sha256": _sha(receipt.read_bytes()),
            "orthogonal_states": {"execution_state": "timeout", "oracle_state": "not_run", "receipt_state": "verified"}}
    spec = {"checker_id": checker, "fixture": "fixture.json", "expected_artifacts": ["report.json", "report.md"]}
    if checker == "index_fallback_integrity/v1":
        fixture = {"events": [
            {"event_id": "e1", "type": "mcp_call", "outcome": "failure"},
            {"event_id": "e2", "type": "artifact_read", "source": "stale", "before_sha256": "1", "after_sha256": "1"},
            {"event_id": "e3", "type": "json_parse", "outcome": "failure"},
            {"event_id": "e4", "type": "match", "mode": "degraded"},
        ]}
        report = {"failure_classes": ["degraded_match", "invalid_json", "live_mcp_failure", "stale_artifact_use"],
                  "cited_event_ids": ["e1", "e2", "e3", "e4"], "receipt_input_sha256s": input_hashes,
                  "stale_artifact_preserved": False, "mcp_healthy": True}
    elif checker == "shared_task_artifact/v1":
        fixture = {"state_axes": [
            {"axis": "execution_state", "failure_values": ["internal_error", "malformed", "timeout", "unavailable"]},
            {"axis": "oracle_state", "failure_values": ["fail", "unverifiable"]},
            {"axis": "receipt_state", "failure_values": ["drift"]}],
            "artifact_facts": [{"path_field": "raw_artifact_path", "hash_fact": "raw_artifact_sha256"},
                               {"path_field": "receipt_path", "hash_fact": "receipt_sha256"}],
            "forbidden_claim_phrases": ["same model behavior", "identical controls", "pure harness ablation"]}
        report = {"raw_prompt_sha256": core["raw_prompt_sha256"], "input_sha256s": input_hashes,
                  "tool_policy_sha256": core["tool_policy_sha256"], "raw_artifact_path": "raw.txt",
                  "receipt_path": "receipt.json", "failure_modes": ["timeout"]}
    elif checker == "paired_friction/v1":
        spec.update(exact_modes=["accountable_receipt", "external_guardrail"], required_safety_controls=["service_safety"])
        fixture = {"observations": [
            {"task_key": key, "mode": mode, "completion": "completed", "friction_events": 0,
             "correction_steps": 0, "safety_controls": {"service_safety": True}}
            for key in ("p1", "p2") for mode in spec["exact_modes"]
        ]}
        report = {"modes": spec["exact_modes"], "task_keys": ["p1", "p2"],
                  "pairs": [{"task_key": key, "modes": spec["exact_modes"]} for key in ("p1", "p2")],
                  "denominator": 2, "aggregates": [
                      {"mode": "accountable_receipt", "denominator": 2, "completion_counts": {"completed": 2}, "friction_events": 0, "correction_steps": 0},
                      {"mode": "external_guardrail", "denominator": 2, "completion_counts": {"completed": 2}, "friction_events": 0, "correction_steps": 0},
                  ], "safety_systems_disabled": True}
    else:
        spec["expected_surfaces"] = ["capability_catalog", "documentation", "roadmap", "schematic_notes"]
        fixture = {"surfaces": [{"surface": name, "path": f"docs/{name}.md", "code_refs": [f"src/{name}.py"]}
                                for name in spec["expected_surfaces"]]}
        for row in fixture["surfaces"]:
            _write(workspace / row["path"], task_id, raw=True)
            _write(workspace / row["code_refs"][0], "pass\n", raw=True)
        report = {"surfaces": json.loads(json.dumps(fixture["surfaces"])), "synchronized": False, "gate_passed": False}
    _write(workspace / "fixture.json", fixture)
    input_hashes["fixture.json"] = _sha((workspace / "fixture.json").read_bytes())
    report.update(task_id=task_id, input_sha256s=report.get("input_sha256s", input_hashes))
    json_path, md_path = attempt / "report.json", attempt / "report.md"
    _write(json_path, report)
    _write(md_path, f"# {task_id}\n", raw=True)
    context = OracleContext(task_id, spec, attempt / "output.json", {json_path.name: json_path, md_path.name: md_path}, input_hashes, core)
    _sync_output(context, report)
    return context, report, fixture
@pytest.mark.parametrize("checker", TASKS)
def test_each_oracle_passes_from_facts_and_ignores_provider_booleans(tmp_path, checker):
    context, _, _ = _case(tmp_path, checker)
    result = evaluate_task_oracle(context); assert (result.state, result.failure_codes) == ("pass", [])
    assert result.checked_artifacts == sorted(result.checked_artifacts, key=lambda row: row["role"]); assert all(len(row["sha256"]) == 64 for row in result.checked_artifacts); assert result.evidence["failure_code_count"] == 0
@pytest.mark.parametrize(("mutation", "code"), [
    ("artifact_set", "artifact_set_mismatch"), ("not_regular", "artifact_not_regular"),
    ("not_utf8", "artifact_not_utf8"), ("empty", "artifact_empty"),
    ("invalid_json", "json_invalid"), ("duplicate_key", "json_duplicate_key"),
    ("task_id", "task_id_mismatch"), ("input_hash", "input_hash_mismatch"),
    ("markdown_id", "markdown_task_id_missing"),
])
def test_common_failures_are_exact(tmp_path, mutation, code):
    context, report, _ = _case(tmp_path, "index_fallback_integrity/v1"); paths = context.artifact_paths
    if mutation == "artifact_set": paths.pop("report.md")
    elif mutation == "not_regular":
        paths["report.md"] = paths["report.md"].parent / "nested" / "report.md"
        paths["report.md"].mkdir(parents=True)
    elif mutation == "not_utf8": paths["report.md"].write_bytes(b"\xff")
    elif mutation == "empty": paths["report.md"].write_bytes(b"")
    elif mutation == "invalid_json": paths["report.json"].write_text("{", encoding="utf-8")
    elif mutation == "duplicate_key": paths["report.json"].write_text('{"task_id":"x","task_id":"y"}', encoding="utf-8")
    elif mutation == "task_id": report["task_id"] = "wrong"
    elif mutation == "input_hash": report["input_sha256s"] = {}
    elif mutation == "markdown_id": paths["report.md"].write_text("# missing", encoding="utf-8")
    if mutation in {"task_id", "input_hash", "markdown_id"}: _sync_output(context, report)
    result = evaluate_task_oracle(context)
    assert result.failure_codes == [code]
    assert result.state == ("malformed" if mutation in {"not_regular", "not_utf8", "empty", "invalid_json", "duplicate_key"} else "fail")
@pytest.mark.parametrize(("checker", "mutation", "codes"), [
    ("index_fallback_integrity/v1", "classes", ["failure_classes_mismatch"]), ("index_fallback_integrity/v1", "citations", ["event_citation_mismatch"]),
    ("index_fallback_integrity/v1", "stale", ["stale_artifact_mutated"]), ("index_fallback_integrity/v1", "health", ["unsupported_mcp_health_claim"]),
    ("index_fallback_integrity/v1", "health_server", ["unsupported_mcp_health_claim"]), ("index_fallback_integrity/v1", "health_succeeded", ["unsupported_mcp_health_claim"]),
    ("index_fallback_integrity/v1", "health_service", ["unsupported_mcp_health_claim"]), ("index_fallback_integrity/v1", "health_status", ["unsupported_mcp_health_claim"]),
    ("index_fallback_integrity/v1", "health_was", ["unsupported_mcp_health_claim"]), ("index_fallback_integrity/v1", "health_endpoint", ["unsupported_mcp_health_claim"]), ("index_fallback_integrity/v1", "health_passed", ["unsupported_mcp_health_claim"]),
    ("index_fallback_integrity/v1", "health_live", ["unsupported_mcp_health_claim"]), ("index_fallback_integrity/v1", "health_reachable", ["unsupported_mcp_health_claim"]), ("index_fallback_integrity/v1", "health_working", ["unsupported_mcp_health_claim"]), ("index_fallback_integrity/v1", "health_works", ["unsupported_mcp_health_claim"]), ("index_fallback_integrity/v1", "health_remains", ["unsupported_mcp_health_claim"]), ("index_fallback_integrity/v1", "health_remained", ["unsupported_mcp_health_claim"]), ("index_fallback_integrity/v1", "health_appears", ["unsupported_mcp_health_claim"]), ("index_fallback_integrity/v1", "health_appeared", ["unsupported_mcp_health_claim"]), ("index_fallback_integrity/v1", "health_seems", ["unsupported_mcp_health_claim"]), ("index_fallback_integrity/v1", "health_responded", ["unsupported_mcp_health_claim"]), ("index_fallback_integrity/v1", "health_colon", ["unsupported_mcp_health_claim"]), ("index_fallback_integrity/v1", "health_newline", ["unsupported_mcp_health_claim"]), ("index_fallback_integrity/v1", "health_semicolon", ["unsupported_mcp_health_claim"]), ("index_fallback_integrity/v1", "health_comma", ["unsupported_mcp_health_claim"]), ("index_fallback_integrity/v1", "health_unrelated_negative", ["unsupported_mcp_health_claim"]), ("index_fallback_integrity/v1", "health_configured_and", ["unsupported_mcp_health_claim"]), ("index_fallback_integrity/v1", "health_configured_but", ["unsupported_mcp_health_claim"]), ("index_fallback_integrity/v1", "health_subject_carry", ["unsupported_mcp_health_claim"]), ("index_fallback_integrity/v1", "health_predicate_coord", ["unsupported_mcp_health_claim"]), ("index_fallback_integrity/v1", "health_unrelated_documentation", []), ("index_fallback_integrity/v1", "health_unrelated_logs", []), ("index_fallback_integrity/v1", "health_yet", ["unsupported_mcp_health_claim"]), ("index_fallback_integrity/v1", "health_structured", ["unsupported_mcp_health_claim"]), ("index_fallback_integrity/v1", "health_nested", ["unsupported_mcp_health_claim"]), ("index_fallback_integrity/v1", "health_structured_sibling", ["unsupported_mcp_health_claim"]), ("index_fallback_integrity/v1", "health_structured_negative", []), ("index_fallback_integrity/v1", "health_structured_unknown", []), ("index_fallback_integrity/v1", "health_structured_key_noise", []), ("index_fallback_integrity/v1", "health_negative", []), ("index_fallback_integrity/v1", "health_unknown", []), ("index_fallback_integrity/v1", "health_neutral", []),
    ("index_fallback_integrity/v1", "receipt_hash", ["receipt_input_hash_mismatch"]), ("shared_task_artifact/v1", "prompt", ["prompt_hash_mismatch"]),
    ("shared_task_artifact/v1", "policy", ["tool_policy_hash_mismatch"]), ("shared_task_artifact/v1", "raw_path", ["raw_artifact_path_invalid"]),
    ("shared_task_artifact/v1", "raw_hash", ["raw_artifact_hash_mismatch"]), ("shared_task_artifact/v1", "modes", ["failure_modes_mismatch"]),
    ("shared_task_artifact/v1", "receipt_path", ["receipt_path_invalid"]), ("shared_task_artifact/v1", "claim", ["forbidden_claim"]),
    ("paired_friction/v1", "mode_set", ["fixture_mode_set_invalid", "fixture_pair_incomplete", "reported_pair_mismatch"]), ("paired_friction/v1", "pair_incomplete", ["fixture_pair_incomplete", "reported_pair_mismatch"]),
    ("paired_friction/v1", "keys", ["reported_task_keys_mismatch"]), ("paired_friction/v1", "pairs", ["reported_pair_mismatch"]),
    ("paired_friction/v1", "reported_modes", ["reported_pair_mismatch"]), ("paired_friction/v1", "denominator", ["denominator_mismatch"]),
    ("paired_friction/v1", "safety", ["fixture_safety_control_disabled"]), ("paired_friction/v1", "safety_string", ["fixture_safety_control_disabled"]),
    ("paired_friction/v1", "safety_int", ["fixture_safety_control_disabled"]), ("paired_friction/v1", "safety_null", ["fixture_safety_control_disabled"]),
    ("paired_friction/v1", "safety_missing", ["fixture_safety_control_disabled"]), ("documentation_maintenance/v1", "surface_fixture", ["fixture_surface_set_invalid", "surface_set_mismatch"]),
    ("documentation_maintenance/v1", "surface_set", ["surface_set_mismatch"]), ("documentation_maintenance/v1", "surface_path", ["surface_path_invalid"]),
    ("documentation_maintenance/v1", "code_refs", ["code_refs_mismatch"]), ("documentation_maintenance/v1", "public_claim", ["claim_language_violation"]),
    ("documentation_maintenance/v1", "scoped_disclaimer", ["claim_language_violation"]), ("documentation_maintenance/v1", "mixed_disclaimer", ["claim_language_violation"]),
    ("documentation_maintenance/v1", "crossing_disclaimer_optimal", ["claim_language_violation"]), ("documentation_maintenance/v1", "optimal_disclaimer_crossing", ["claim_language_violation"]), ("documentation_maintenance/v1", "crossing_occurrence", ["claim_language_violation"]), ("documentation_maintenance/v1", "colon_disclaimer", ["claim_language_violation"]), ("documentation_maintenance/v1", "parenthetical_disclaimer", ["claim_language_violation"]), ("documentation_maintenance/v1", "claim_have_solved", ["claim_language_violation"]), ("documentation_maintenance/v1", "claim_have_proven", ["claim_language_violation"]), ("documentation_maintenance/v1", "claim_passive_solved", ["claim_language_violation"]), ("documentation_maintenance/v1", "claim_resolved", ["claim_language_violation"]), ("documentation_maintenance/v1", "claim_settled", ["claim_language_violation"]), ("documentation_maintenance/v1", "claim_shared_object", ["claim_language_violation"]), ("documentation_maintenance/v1", "claim_passive_modifier", ["claim_language_violation"]), ("documentation_maintenance/v1", "claim_multi_coordination", ["claim_language_violation"]), ("documentation_maintenance/v1", "claim_arbitrary_coordination", ["claim_language_violation"]), ("documentation_maintenance/v1", "claim_active_negative", []), ("documentation_maintenance/v1", "claim_open_negative", []), ("documentation_maintenance/v1", "claim_cannot_negative", []), ("documentation_maintenance/v1", "claim_cannot_open", []), ("documentation_maintenance/v1", "claim_no_negative", []), ("documentation_maintenance/v1", "claim_article_optimal", []), ("documentation_maintenance/v1", "claim_article_crossing", []), ("documentation_maintenance/v1", "claim_no_article", []), ("documentation_maintenance/v1", "claim_that_article", []), ("documentation_maintenance/v1", "claim_cannot_establish", []), ("documentation_maintenance/v1", "claim_negative", []),
    ("index_fallback_integrity/v1", "health_available_documentation", []), ("index_fallback_integrity/v1", "health_structured_prior_failure", ["unsupported_mcp_health_claim"]), ("index_fallback_integrity/v1", "health_structured_documentation", []), ("index_fallback_integrity/v1", "health_diagnostics", ["unsupported_mcp_health_claim"]), ("index_fallback_integrity/v1", "health_sibling_diagnostics", ["unsupported_mcp_health_claim"]), ("index_fallback_integrity/v1", "health_checks", ["unsupported_mcp_health_claim"]), ("index_fallback_integrity/v1", "health_latest", ["unsupported_mcp_health_claim"]), ("index_fallback_integrity/v1", "health_modifier", ["unsupported_mcp_health_claim"]), ("index_fallback_integrity/v1", "health_notes_documentation", []), ("index_fallback_integrity/v1", "health_notes_explicit", []), ("index_fallback_integrity/v1", "health_documentation_explicit", []), ("index_fallback_integrity/v1", "health_not_yet", []),
    ("documentation_maintenance/v1", "claim_demonstrative", ["claim_language_violation"]), ("documentation_maintenance/v1", "claim_present", ["claim_language_violation"]), ("documentation_maintenance/v1", "claim_unknown_solved", []), ("documentation_maintenance/v1", "claim_not_known_optimal", []), ("documentation_maintenance/v1", "claim_tested_whether", []), ("documentation_maintenance/v1", "claim_conditional", []), ("documentation_maintenance/v1", "claim_not_determine", []), ("documentation_maintenance/v1", "claim_remains_unknown", []), ("documentation_maintenance/v1", "claim_unknown_then_value", ["claim_language_violation"]), ("documentation_maintenance/v1", "claim_undetermined_then_value", ["claim_language_violation"]),
])
def test_task_failure_sets_are_exact(tmp_path, checker, mutation, codes):
    context, report, fixture = _case(tmp_path, checker)
    if checker.startswith("index"):
        if mutation == "classes": report["failure_classes"] = []
        elif mutation == "citations": report["cited_event_ids"] = []
        elif mutation == "stale": fixture["events"][1]["after_sha256"] = "2"
        elif mutation in {"health_available_documentation", "health_structured_prior_failure", "health_structured_documentation", "health_diagnostics", "health_sibling_diagnostics", "health_checks", "health_latest", "health_modifier", "health_notes_documentation", "health_notes_explicit", "health_documentation_explicit", "health_not_yet"}:
            value = {"health_available_documentation": "MCP is configured and available documentation follows.", "health_structured_prior_failure": {"mcp": {"health": "healthy despite an earlier failure"}}, "health_structured_documentation": {"mcp": {"documentation": {"status": "available"}}}, "health_diagnostics": {"mcp": {"diagnostics": {"health": "healthy"}}}, "health_sibling_diagnostics": {"service": "mcp", "diagnostics": {"health": "healthy"}}, "health_checks": {"mcp": {"checks": [{"status": "available"}]}}, "health_latest": {"mcp": {"health": "previously failed, now healthy"}}, "health_modifier": "MCP is configured and healthy now.", "health_notes_documentation": {"mcp": {"health_notes": {"documentation": "available"}}}, "health_notes_explicit": {"mcp": {"notes": {"health": "healthy"}}}, "health_documentation_explicit": {"mcp": {"documentation": {"health": "healthy"}}}, "health_not_yet": {"mcp_status": "not yet healthy"}}[mutation]; report.update(value) if isinstance(value, dict) else context.artifact_paths["report.md"].write_text(f"{context.task_id}\n{value}", encoding="utf-8")
        elif mutation.startswith("health"):
            claims = {"health": "MCP is healthy.", "health_server": "MCP server is healthy.", "health_succeeded": "MCP health check succeeded.", "health_service": "MCP service is operational.", "health_status": "MCP status: available.", "health_was": "MCP server was healthy.",
                      "health_endpoint": "MCP endpoint is healthy.", "health_passed": "MCP passed its health check.", "health_live": "MCP is live.", "health_reachable": "MCP is reachable.", "health_working": "MCP is working.", "health_works": "MCP works.", "health_remains": "MCP remains healthy.", "health_remained": "MCP remained healthy.", "health_appears": "MCP appears healthy.", "health_appeared": "MCP appeared healthy.", "health_seems": "MCP seems healthy.", "health_responded": "MCP responded.", "health_colon": "MCP status is unknown: MCP is healthy.", "health_newline": "MCP status is unknown\nMCP is healthy.", "health_semicolon": "MCP status is unknown; MCP is healthy.", "health_comma": "MCP status is unknown, MCP is healthy.", "health_unrelated_negative": "MCP is healthy despite not authenticated.", "health_configured_and": "MCP is configured and healthy.", "health_configured_but": "MCP is configured but remains healthy.", "health_subject_carry": "MCP is not authenticated but is healthy.", "health_predicate_coord": "MCP is configured, healthy, and reachable.", "health_unrelated_documentation": "MCP is configured and documentation is available.", "health_unrelated_logs": "MCP is configured, but logs are available.", "health_yet": "MCP is configured yet healthy.", "health_structured": {"mcp_health": "healthy"}, "health_nested": {"diagnostics": {"mcp": {"health": {"assessment": {"value": "healthy"}}}}}, "health_structured_sibling": {"service": "mcp", "health": "healthy"}, "health_structured_negative": {"mcp_status": "not healthy"}, "health_structured_unknown": {"service": "mcp", "status": "unverified healthy"}, "health_structured_key_noise": {"xmcp_status": "healthy"}, "health_negative": "MCP is not reachable.", "health_unknown": "MCP status is unknown.", "health_neutral": "MCP is configured."}; value = claims[mutation]; report.update(value) if isinstance(value, dict) else context.artifact_paths["report.md"].write_text(f"{context.task_id}\n{value}", encoding="utf-8")
        else: report["receipt_input_sha256s"] = {}
    elif checker.startswith("shared"):
        field = {"prompt": "raw_prompt_sha256", "policy": "tool_policy_sha256", "modes": "failure_modes"}.get(mutation)
        if field: report[field] = [] if mutation == "modes" else "0" * 64
        elif mutation == "raw_path": report["raw_artifact_path"] = "../raw.txt"
        elif mutation == "raw_hash": Path(context.scorecard_core["attempt_dir"], "raw.txt").write_text("changed", encoding="utf-8")
        elif mutation == "receipt_path": report["receipt_path"] = "../receipt.json"
        else: context.artifact_paths["report.md"].write_text(f"{context.task_id}\nPure harness ablation.", encoding="utf-8")
    elif checker.startswith("paired"):
        if mutation == "mode_set": fixture["observations"][0]["mode"] = "other"
        elif mutation == "pair_incomplete": fixture["observations"].pop()
        elif mutation == "keys": report["task_keys"] = []
        elif mutation == "pairs": report["pairs"] = []
        elif mutation == "reported_modes": report["modes"] = []
        elif mutation == "denominator": report["denominator"] = 9
        else:
            controls = fixture["observations"][0]["safety_controls"]
            if mutation == "safety_missing": controls.pop("service_safety")
            else: controls["service_safety"] = {"safety": False, "safety_string": "true", "safety_int": 1, "safety_null": None}[mutation]
    else:
        if mutation == "surface_fixture": fixture["surfaces"][0]["surface"] = "other"
        elif mutation == "surface_set": report["surfaces"].pop()
        elif mutation == "surface_path": report["surfaces"][0]["path"] = "../outside.md"
        elif mutation == "code_refs": report["surfaces"][0]["code_refs"] = []
        else:
            claim = {"scoped_disclaimer": "Optimality is not claimed\n- We solved the open problem.", "mixed_disclaimer": "Optimality is not claimed, but we solved the open problem.", "crossing_disclaimer_optimal": "Crossing number is not claimed and this is an optimal drawing.",
                     "optimal_disclaimer_crossing": "Optimality is not claimed and the crossing number of G is 5.", "crossing_occurrence": "Crossing number is not claimed and the crossing number of G is 5.", "colon_disclaimer": "Crossing number is not claimed: We solved the open problem.", "parenthetical_disclaimer": "Crossing number is not claimed (We solved the open problem).", "claim_have_solved": "We have solved the open problem.", "claim_have_proven": "We have proven the open problem.", "claim_passive_solved": "The open problem was solved.", "claim_resolved": "We resolved the open problem.", "claim_settled": "We settled the open problem.", "claim_shared_object": "We solved and published the open problem.", "claim_passive_modifier": "The open problem was conclusively solved.", "claim_multi_coordination": "We solved, documented, and published the open problem.", "claim_arbitrary_coordination": "We solved and wrote about the open problem.", "claim_active_negative": "We do not claim optimality.", "claim_open_negative": "We do not claim to have solved the open problem.", "claim_cannot_negative": "We cannot prove optimality.", "claim_cannot_open": "We cannot claim to have solved the open problem.", "claim_no_negative": "No claim of the crossing number is made.", "claim_article_optimal": "We do not claim an optimal drawing.", "claim_article_crossing": "We do not claim the crossing number.", "claim_no_article": "No claim of an optimal drawing is made.", "claim_that_article": "We do not claim that this is an optimal drawing.", "claim_cannot_establish": "We cannot establish an optimal drawing.", "claim_negative": "Optimality is not claimed."}.get(mutation, "We solved the open problem."); context.artifact_paths["report.md"].write_text(f"{context.task_id}\n{claim}", encoding="utf-8")
            claim = {"claim_demonstrative": "We solved this open problem.", "claim_present": "This work solves the open problem.", "claim_unknown_solved": "It remains unknown whether the open problem was solved.", "claim_not_known_optimal": "This is not known to be an optimal drawing.", "claim_tested_whether": "We tested whether the open problem was solved.", "claim_conditional": "If we solved the open problem, the report would change.", "claim_not_determine": "We did not determine the crossing number.", "claim_remains_unknown": "The crossing number remains unknown.", "claim_unknown_then_value": "The crossing number remains unknown, but equals 5.", "claim_undetermined_then_value": "We did not determine the crossing number, but it is 5."}.get(mutation, claim); context.artifact_paths["report.md"].write_text(f"{context.task_id}\n{claim}", encoding="utf-8")
    fixture_path = Path(context.scorecard_core["workspace_root"]) / "fixture.json"
    _write(fixture_path, fixture)
    context.expected_input_sha256s["fixture.json"] = _sha(fixture_path.read_bytes())
    report["input_sha256s"] = context.expected_input_sha256s
    _sync_output(context, report)
    assert evaluate_task_oracle(context).failure_codes == codes
def test_json_order_and_whitespace_do_not_change_verdict(tmp_path):
    context, report, _ = _case(tmp_path, "index_fallback_integrity/v1")
    context.artifact_paths["report.json"].write_text(json.dumps(report, sort_keys=True, indent=7), encoding="utf-8")
    assert evaluate_task_oracle(context).state == "pass"
@pytest.mark.parametrize("case", ["missing", "utf8", "json", "duplicate", "envelope", "null", "number", "array"])
def test_raw_output_boundary_is_malformed_before_checker(tmp_path, case):
    context, _, _ = _case(tmp_path, "index_fallback_integrity/v1")
    if case == "missing": context.raw_output_path.unlink()
    elif case == "utf8": context.raw_output_path.write_bytes(b"\xff")
    elif case == "json": context.raw_output_path.write_text("{", encoding="utf-8")
    elif case == "duplicate": context.raw_output_path.write_text('{"artifacts":{},"artifacts":{}}', encoding="utf-8")
    elif case == "envelope": _write(context.raw_output_path, {"wrong": {}})
    else: context.raw_output_path.write_text({"null": "null", "number": "7", "array": "[]"}[case], encoding="utf-8")
    result = evaluate_task_oracle(context)
    assert result.state == "malformed"
    assert result.failure_codes == ["json_invalid"]
def test_mapping_key_cannot_hide_wrong_artifact_basename(tmp_path):
    context, report, _ = _case(tmp_path, "index_fallback_integrity/v1")
    wrong = Path(context.scorecard_core["attempt_dir"]) / "other.md"
    wrong.write_text(f"# {context.task_id}\n", encoding="utf-8")
    context.artifact_paths["report.md"] = wrong
    _sync_output(context, report)
    assert evaluate_task_oracle(context).failure_codes == ["artifact_set_mismatch"]
def test_paired_oracle_derives_raw_observation_aggregates(tmp_path):
    context, report, fixture = _case(tmp_path, "paired_friction/v1")
    fixture["observations"][0].update(completion="blocked", friction_events=4, correction_steps=2)
    path = Path(context.scorecard_core["workspace_root"]) / "fixture.json"
    _write(path, fixture)
    context.expected_input_sha256s["fixture.json"] = _sha(path.read_bytes())
    report["input_sha256s"] = context.expected_input_sha256s
    _sync_output(context, report)
    assert evaluate_task_oracle(context).failure_codes == ["reported_pair_mismatch"]
def test_shared_oracle_uses_bound_fixture_state_facts(tmp_path):
    context, report, fixture = _case(tmp_path, "shared_task_artifact/v1")
    fixture["state_axes"][0]["failure_values"].remove("timeout")
    path = Path(context.scorecard_core["workspace_root"]) / "fixture.json"
    _write(path, fixture)
    context.expected_input_sha256s["fixture.json"] = _sha(path.read_bytes())
    report["input_sha256s"] = context.expected_input_sha256s
    _sync_output(context, report)
    assert evaluate_task_oracle(context).failure_codes == ["failure_modes_mismatch"]
def test_admitted_fixture_hash_is_bound_before_checker(tmp_path):
    context, _, _ = _case(tmp_path, "shared_task_artifact/v1")
    (Path(context.scorecard_core["workspace_root"]) / "fixture.json").write_text("{}", encoding="utf-8")
    assert evaluate_task_oracle(context).failure_codes == ["input_hash_mismatch"]
@pytest.mark.parametrize(("checker", "roles"), [
    ("index_fallback_integrity/v1", {"raw_output", "input_fixture", "provider:report.json", "provider:report.md"}),
    ("shared_task_artifact/v1", {"raw_output", "input_fixture", "provider:report.json", "provider:report.md", "raw_artifact", "receipt"}),
    ("documentation_maintenance/v1", {"raw_output", "input_fixture", "provider:report.json", "provider:report.md", *(f"workspace:{kind}:{name}{':0' if kind == 'code_ref' else ''}" for kind in ("surface", "code_ref") for name in ("capability_catalog", "documentation", "roadmap", "schematic_notes"))}),
])
def test_checked_artifacts_cover_every_inspected_file(tmp_path, checker, roles):
    context, _, _ = _case(tmp_path, checker)
    assert {row["role"] for row in evaluate_task_oracle(context).checked_artifacts} == roles
@pytest.mark.parametrize(("checker", "field", "value"), [
    ("index_fallback_integrity/v1", "provider_root", None), ("index_fallback_integrity/v1", "provider_root", 7), ("index_fallback_integrity/v1", "provider_root", []),
    ("shared_task_artifact/v1", "failure_modes", None), ("shared_task_artifact/v1", "raw_prompt_sha256", "A" * 64),
    ("shared_task_artifact/v1", "tool_policy_sha256", 7), ("shared_task_artifact/v1", "raw_artifact_path", ""),
    ("shared_task_artifact/v1", "receipt_path", None), ("paired_friction/v1", "aggregates", None),
    ("documentation_maintenance/v1", "surfaces", None), ("documentation_maintenance/v1", "surface", []),
    ("documentation_maintenance/v1", "path", 7), ("documentation_maintenance/v1", "code_refs", [[]]),
])
def test_malformed_required_types_never_raise(tmp_path, checker, field, value):
    context, report, _ = _case(tmp_path, checker)
    if field == "provider_root": _write(context.artifact_paths["report.json"], value)
    elif checker.startswith("documentation"):
        if field == "surfaces": report[field] = value
        else: report["surfaces"][0][field] = value
    else: report[field] = value
    if field != "provider_root": _sync_output(context, report)
    result = evaluate_task_oracle(context)
    assert (result.state, result.failure_codes) == ("malformed", ["json_invalid"])
@pytest.mark.parametrize("spec", [{}, {"checker_id": "missing/v1"}])
def test_missing_or_unknown_checker_is_unverifiable(tmp_path, spec):
    context, _, _ = _case(tmp_path, "index_fallback_integrity/v1")
    context = OracleContext(context.task_id, spec, context.raw_output_path, context.artifact_paths, context.expected_input_sha256s, context.scorecard_core)
    assert evaluate_task_oracle(context).state == "unverifiable"
def test_missing_admitted_fixture_is_unverifiable(tmp_path):
    context, _, _ = _case(tmp_path, "index_fallback_integrity/v1"); context.oracle_spec["fixture"] = "missing.json"
    result = evaluate_task_oracle(context)
    assert (result.state, result.evidence) == ("unverifiable", {"reason": "fixture_unavailable"})
@pytest.mark.parametrize(("field", "value"), [("workspace_root", ""), ("workspace_root", "missing"),
                                                ("attempt_dir", ""), ("attempt_dir", "missing")])
def test_executor_roots_must_be_explicit_existing_directories(tmp_path, field, value):
    context, _, _ = _case(tmp_path, "shared_task_artifact/v1"); context.scorecard_core[field] = str(tmp_path / value) if value else value
    assert evaluate_task_oracle(context).state == "malformed"
def test_common_validation_accumulates_codes_and_artifact_hashes(tmp_path):
    context, report, _ = _case(tmp_path, "index_fallback_integrity/v1"); report.update(task_id="wrong", input_sha256s={})
    context.artifact_paths["report.md"].write_text("", encoding="utf-8")
    _write(context.artifact_paths["report.json"], report); _write(context.raw_output_path, {"artifacts": {"report.json": report, "report.md": ""}})
    result = evaluate_task_oracle(context)
    assert result.failure_codes == ["artifact_empty", "input_hash_mismatch", "task_id_mismatch"]
    assert {row["role"] for row in result.checked_artifacts} >= {"raw_output", "provider:report.json", "provider:report.md"}
@pytest.mark.parametrize("target", ["raw", "report.json", "report.md"])
@pytest.mark.parametrize("kind", ["outside", "traversal", "escape"])
def test_attempt_artifacts_reject_outside_traversal_and_resolved_escape(tmp_path, monkeypatch, target, kind):
    context, _, _ = _case(tmp_path, "index_fallback_integrity/v1"); source = context.raw_output_path if target == "raw" else context.artifact_paths[target]
    outside = tmp_path / f"outside-{target}"; outside.write_bytes(source.read_bytes())
    if kind == "outside": candidate = outside
    elif kind == "traversal": candidate = source.parent / "nested" / ".." / source.name
    else:
        candidate, original = source.parent / f"escape-{target}", Path.resolve
        candidate.write_bytes(source.read_bytes()); monkeypatch.setattr(Path, "resolve", lambda path, *a, **kw: outside if path.name == candidate.name else original(path, *a, **kw))
    if target == "raw": context = OracleContext(context.task_id, context.oracle_spec, candidate, context.artifact_paths, context.expected_input_sha256s, context.scorecard_core)
    else: context.artifact_paths[target] = candidate
    assert evaluate_task_oracle(context).state == "malformed"
@pytest.mark.parametrize(("kind", "value"), [("missing", None), ("extra", "x"), ("execution_state", "bogus"), ("oracle_state", "bogus"), ("receipt_state", "bogus"), ("execution_state", "launched"), ("oracle_state", "fail"), ("receipt_state", "drift"), ("receipt_state", "not_emitted")])
def test_shared_states_require_exact_keys_and_approved_values(tmp_path, kind, value):
    context, report, _ = _case(tmp_path, "shared_task_artifact/v1"); states = context.scorecard_core["orthogonal_states"]
    if kind == "missing": states.pop("oracle_state")
    elif kind == "extra": states["extra"] = value
    else: states[kind] = value
    if value not in {None, "x", "bogus"}: report["failure_modes"] = {"launched": [], "fail": ["fail", "timeout"], "drift": ["drift", "timeout"], "not_emitted": ["timeout"]}[value]
    _sync_output(context, report); assert evaluate_task_oracle(context).state == ("malformed" if value in {None, "x", "bogus"} else "pass")
def test_oracle_hashes_each_immutable_file_buffer_once(tmp_path, monkeypatch):
    context, _, _ = _case(tmp_path, "shared_task_artifact/v1"); target, counts = context.artifact_paths["report.json"], {}
    original, expected = {"bytes": Path.read_bytes, "text": Path.read_text}, Path.read_bytes(target)
    def observed(path, mode, *args, **kwargs):
        counts[path] = counts.get(path, 0) + 1; data = original[mode](path, *args, **kwargs)
        (path.write_bytes(b"mutated") if path == target and counts[path] == 1 else None); return data
    monkeypatch.setattr(Path, "read_bytes", lambda path, *a, **kw: observed(path, "bytes", *a, **kw)); monkeypatch.setattr(Path, "read_text", lambda path, *a, **kw: observed(path, "text", *a, **kw))
    result = evaluate_task_oracle(context); assert result.state == "pass" and set(counts.values()) == {1}
    assert next(row["sha256"] for row in result.checked_artifacts if row["role"] == "provider:report.json") == _sha(expected)
