from __future__ import annotations


def _answered(task_id: str, answer: dict, citations: list[str]) -> dict:
    return {"task_id": task_id, "verdict": "ANSWERED", "answer": answer, "citations": citations}


def _unverifiable(task_id: str, missing: list[str], blocked: list[str], citations: list[str]) -> dict:
    return {
        "task_id": task_id,
        "verdict": "UNVERIFIABLE",
        "answer": None,
        "missing_evidence": missing,
        "claims_not_made": blocked,
        "citations": citations,
    }


def _record(record_id: str, record_type: str, **fields) -> dict:
    return {"record_id": record_id, "record_type": record_type, "fields": fields}


def _case_data() -> dict[str, tuple[list[dict], dict]]:
    return {
        "kv-msr-001-incident-reconstruction": (
            [
                _record("asset-catalog:omega-742", "asset", case_id="OMEGA-742", owner="ops", component="pump"),
                _record("event-ledger:e9001", "event", case_id="OMEGA-742", state="triage", sequence=1, superseded_by="event-ledger:e9107"),
                _record("event-ledger:e9107", "event", case_id="OMEGA-742", state="repair", sequence=2, supersedes="event-ledger:e9001"),
                _record("exception-table:x42", "exception", case_id="OMEGA-742", when_state="repair", required_action="replace seal", due_date="2026-01-17"),
                _record("event-ledger:decoy", "event", case_id="OTHER", state="complete", sequence=99),
            ],
            _answered(
                "kv-msr-001-incident-reconstruction",
                {
                    "case_id": "OMEGA-742",
                    "owner": "ops",
                    "component": "pump",
                    "current_state": "repair",
                    "latest_sequence": 2,
                    "required_action": "replace seal",
                    "due_date": "2026-01-17",
                },
                ["asset-catalog:omega-742", "event-ledger:e9107", "exception-table:x42"],
            ),
        ),
        "kv-msr-002-route-reconstruction": (
            [
                _record("shipment:bravo-6", "shipment", shipment_id="B6", base_crates=10, temperature_mode="chilled"),
                _record("route-update:u700", "route_update", shipment_id="B6", status="APPROVED", revision=1, route=["SEA", "PDX"]),
                _record("route-update:u772", "route_update", shipment_id="B6", status="APPROVED", revision=2, route=["SEA", "SFO"]),
                _record("route-update:u900", "route_update", shipment_id="B6", status="PENDING", revision=3, route=["SEA", "LAX"]),
                _record("capacity-override:o204", "capacity_override", shipment_id="B6", status="APPROVED", max_crates=8),
                _record("capacity-override:o300", "capacity_override", shipment_id="B6", status="APPROVED", max_crates=9),
                _record("cancellation:c118", "cancellation", shipment_id="B6", status="APPROVED", cancelled_crates=2, release_gate="manual-qc"),
            ],
            _answered(
                "kv-msr-002-route-reconstruction",
                {"shipment_id": "B6", "route": ["SEA", "SFO"], "accepted_crates": 6, "temperature_mode": "chilled", "release_gate": "manual-qc"},
                ["shipment:bravo-6", "route-update:u772", "capacity-override:o204", "cancellation:c118"],
            ),
        ),
        "kv-rap-001-policy-precedence": (
            [
                _record("policy:ctx-window:rev12", "policy_revision", policy_id="ctx-window", revision=12, status="APPROVED", context_tokens=4096, max_output_tokens=512, cache_reuse_between_arms=False),
                _record("policy:ctx-window:rev14", "policy_revision", policy_id="ctx-window", revision=14, status="APPROVED", context_tokens=8192, max_output_tokens=768, cache_reuse_between_arms=True),
                _record("policy:ctx-window:rev15", "policy_revision", policy_id="ctx-window", revision=15, status="PENDING", context_tokens=32768, max_output_tokens=1024, cache_reuse_between_arms=True),
                _record("override:unsigned-river", "override", policy_id="ctx-window", status="UNSIGNED", approver="river", max_output_tokens=2048),
                _record("approver-registry:ctx-window", "approver_registry", policy_id="ctx-window", authorized_approvers=["ops-lead"]),
            ],
            _answered(
                "kv-rap-001-policy-precedence",
                {
                    "policy_id": "ctx-window",
                    "active_revision": 14,
                    "context_tokens": 8192,
                    "max_output_tokens": 768,
                    "cache_reuse_between_arms": True,
                    "reason": "latest_approved_revision",
                },
                ["policy:ctx-window:rev12", "policy:ctx-window:rev14", "override:unsigned-river", "approver-registry:ctx-window"],
            ),
        ),
        "kv-rap-002-release-approval": (
            [
                _record("source:serving:43640b2", "source_candidate", candidate="43640b2", source_state="reviewed"),
                _record("review:serving:independent-pass", "review", candidate="43640b2", decision="pass"),
                _record("ci:heavy-source:pending", "ci", candidate="43640b2", heavy_source_tests="pending"),
                _record("approval:default-change:absent", "approval", candidate="43640b2", default_change_approved=False),
            ],
            _answered(
                "kv-rap-002-release-approval",
                {
                    "candidate": "43640b2",
                    "source_state": "reviewed",
                    "allowed_use": "diagnostic_gate_only",
                    "default_change_approved": False,
                    "blockers": ["heavy_source_tests_pending", "no_default_change_approval"],
                },
                ["source:serving:43640b2", "review:serving:independent-pass", "ci:heavy-source:pending", "approval:default-change:absent"],
            ),
        ),
        "kv-cdr-001-retention-authority": (
            [
                _record("operator-handoff:kv-retention", "retention_rule", authority_rank=1, retention_days=30, public_copy_allowed=False, promotion_requires=["review"], note="operator"),
                _record("project-agent:temp-retention", "retention_rule", authority_rank=2, retention_days=7, public_copy_allowed=True, promotion_requires=[], note="agent"),
                _record("roadmap:artifact-retention", "retention_rule", authority_rank=3, retention_days=14, public_copy_allowed=False, promotion_requires=["hash"]),
                _record("stale-transcript:retention", "retention_rule", authority_rank=4, retention_days=90, public_copy_allowed=True, promotion_requires=["none"]),
            ],
            _answered(
                "kv-cdr-001-retention-authority",
                {
                    "retention_days": 30,
                    "public_copy_allowed": False,
                    "promotion_requires": ["review"],
                    "winning_authority": "operator-handoff:kv-retention",
                    "losing_conflicts": ["project-agent:temp-retention", "roadmap:artifact-retention", "stale-transcript:retention"],
                },
                ["operator-handoff:kv-retention", "project-agent:temp-retention", "roadmap:artifact-retention", "stale-transcript:retention"],
            ),
        ),
        "kv-cdr-002-endpoint-authority": (
            [
                _record("live-process:ollama-q8", "endpoint_evidence", authority_rank=1, endpoint_url="http://localhost:11434", context_tokens=8192, cache_type_k="q8_0", cache_type_v="q8_0", flash_attention=True),
                _record("profile-json:ollama-8192", "endpoint_evidence", authority_rank=2, endpoint_url="http://localhost:11434", context_tokens=8192, cache_type_k="q4_0", cache_type_v="q4_0", flash_attention=False),
                _record("docs:serving-defaults", "endpoint_evidence", authority_rank=3, endpoint_url="http://localhost:8000", context_tokens=4096, cache_type_k="default", cache_type_v="default", flash_attention=False),
                _record("memory-note:old-port", "endpoint_evidence", authority_rank=4, endpoint_url="http://localhost:9999", context_tokens=2048, cache_type_k="old", cache_type_v="old", flash_attention=False),
            ],
            _answered(
                "kv-cdr-002-endpoint-authority",
                {
                    "endpoint_url": "http://localhost:11434",
                    "context_tokens": 8192,
                    "cache_type_k": "q8_0",
                    "cache_type_v": "q8_0",
                    "flash_attention": True,
                    "winning_authority": "live-process:ollama-q8",
                },
                ["live-process:ollama-q8", "profile-json:ollama-8192", "docs:serving-defaults", "memory-note:old-port"],
            ),
        ),
        "kv-sta-001-endpoint-gate-argv": (
            [
                _record("tool-schema:run_model_endpoint_gate", "tool_schema", script="scripts/run_model_endpoint_gate.py", allowed_args=["--profile-artifact", "--models", "--backends", "--prompt", "--timeout-seconds", "--max-tokens", "--seed", "--out", "--markdown-out", "--run-id"]),
                _record("operator-request:gate-32b", "operator_request", model="32b", backend="ollama", prompt="prompts/gate.txt", timeout_seconds="45", max_tokens="768", seed="123", run_id="gate-run"),
                _record("path-contract:temp-only", "path_contract", root="scratch/kv", cwd="scratch/kv/worktree", profile="profiles/endpoint.json", out="checks/gate.json", markdown_out="checks/gate.md"),
            ],
            _answered(
                "kv-sta-001-endpoint-gate-argv",
                {
                    "argv": [
                        "python", "scripts/run_model_endpoint_gate.py",
                        "--profile-artifact", "scratch/kv/profiles/endpoint.json",
                        "--models", "32b",
                        "--backends", "ollama",
                        "--prompt", "prompts/gate.txt",
                        "--timeout-seconds", "45",
                        "--max-tokens", "768",
                        "--seed", "123",
                        "--out", "scratch/kv/checks/gate.json",
                        "--markdown-out", "scratch/kv/checks/gate.md",
                        "--run-id", "gate-run",
                    ],
                    "cwd": "scratch/kv/worktree",
                },
                ["tool-schema:run_model_endpoint_gate", "operator-request:gate-32b", "path-contract:temp-only"],
            ),
        ),
        "kv-sta-002-manifest-argv": (
            [
                _record("tool-schema:run_agentic_task_set_manifest", "tool_schema", script="scripts/run_agentic_task_set_manifest.py", allowed_args=["--task-set", "--adapter", "--artifact-dir", "--provider-roles", "--out", "--markdown-out", "--run-id"]),
                _record("operator-request:manifest-kv", "operator_request", provider_roles="local_kv_f16,local_kv_q8_0", run_id="manifest-run"),
                _record("path-contract:temp-only", "path_contract", root="scratch/kv", cwd="scratch/kv/worktree", task_set="task-set.json", adapter="adapter.json", artifact_dir="attempts", out="checks/manifest.json", markdown_out="checks/manifest.md"),
            ],
            _answered(
                "kv-sta-002-manifest-argv",
                {
                    "argv": [
                        "python", "scripts/run_agentic_task_set_manifest.py",
                        "--task-set", "scratch/kv/task-set.json",
                        "--adapter", "scratch/kv/adapter.json",
                        "--artifact-dir", "scratch/kv/attempts",
                        "--provider-roles", "local_kv_f16,local_kv_q8_0",
                        "--out", "scratch/kv/checks/manifest.json",
                        "--markdown-out", "scratch/kv/checks/manifest.md",
                        "--run-id", "manifest-run",
                    ],
                    "cwd": "scratch/kv/worktree",
                },
                ["tool-schema:run_agentic_task_set_manifest", "operator-request:manifest-kv", "path-contract:temp-only"],
            ),
        ),
        "kv-rsm-001-lane-symbol-match": (
            [
                _record("repo-file:harness/lanes.py", "repo_excerpt", role="authoritative_registry", path="harness/lanes.py"),
                _record("symbol:LANE_REGISTRY", "symbol", path="harness/lanes.py", symbol="LANE_REGISTRY"),
                _record("symbol:lane_for_task", "symbol", path="harness/lanes.py", symbol="lane_for_task"),
                _record("repo-file:WORKSPACE-INDEX.md", "repo_excerpt", role="supporting_doc", path="WORKSPACE-INDEX.md"),
            ],
            _answered(
                "kv-rsm-001-lane-symbol-match",
                {"registry_file": "harness/lanes.py", "registry_symbol": "LANE_REGISTRY", "resolver_symbol": "lane_for_task", "supporting_doc": "WORKSPACE-INDEX.md"},
                ["repo-file:harness/lanes.py", "symbol:LANE_REGISTRY", "symbol:lane_for_task", "repo-file:WORKSPACE-INDEX.md"],
            ),
        ),
        "kv-rsm-002-checker-reference-match": (
            [
                _record("repo-file:harness/cross_harness_oracles.py", "repo_excerpt", path="harness/cross_harness_oracles.py"),
                _record("repo-file:harness/cross_harness_checkers.py", "repo_excerpt", path="harness/cross_harness_checkers.py"),
                _record("symbol:_CHECKERS", "symbol", path="harness/cross_harness_oracles.py", symbol="_CHECKERS"),
                _record("checker:evidence_bound_reporting/v1", "checker", checker_id="evidence_bound_reporting/v1", file="harness/cross_harness_checkers.py"),
            ],
            _answered(
                "kv-rsm-002-checker-reference-match",
                {
                    "registration_file": "harness/cross_harness_oracles.py",
                    "graded_checker_file": "harness/cross_harness_checkers.py",
                    "registry_symbol": "_CHECKERS",
                    "checker_id": "evidence_bound_reporting/v1",
                },
                ["repo-file:harness/cross_harness_oracles.py", "repo-file:harness/cross_harness_checkers.py", "symbol:_CHECKERS", "checker:evidence_bound_reporting/v1"],
            ),
        ),
        "kv-abst-001-f16-settings-missing": (
            [
                _record("pilot:comparison", "pilot", f16_runner_arguments_captured=False),
                _record("pilot:q8-runtime-settings", "pilot", q8_runner_arguments_captured=True),
                _record("pilot:f16-empty-logs", "pilot", log_rows=0),
                _record("rule:treatment-compliance", "rule", required_evidence="f16_runner_arguments"),
            ],
            _unverifiable(
                "kv-abst-001-f16-settings-missing",
                ["f16_runner_arguments"],
                ["treatment_compliance_proven", "latency_superiority", "quality_noninferiority"],
                ["pilot:comparison", "pilot:q8-runtime-settings", "pilot:f16-empty-logs", "rule:treatment-compliance"],
            ),
        ),
        "kv-abst-002-frontier-comparison-missing": (
            [
                _record("spec:frontier-comparison", "spec", required=["named_endpoints", "permissions"]),
                _record("evidence:named-endpoints-absent", "missing_evidence", item="named_endpoints", present=False),
                _record("evidence:permissions-absent", "missing_evidence", item="permissions", present=False),
                _record("rule:no-equivalence-from-diagnostic", "rule", forbidden_claims=["frontier_equivalence", "production_readiness"]),
            ],
            _unverifiable(
                "kv-abst-002-frontier-comparison-missing",
                ["named_endpoints", "permissions"],
                ["frontier_equivalence", "production_readiness"],
                ["spec:frontier-comparison", "evidence:named-endpoints-absent", "evidence:permissions-absent", "rule:no-equivalence-from-diagnostic"],
            ),
        ),
    }


CASES = _case_data()


CASES = _case_data()
