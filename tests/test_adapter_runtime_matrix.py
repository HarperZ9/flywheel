import json

from harness.adapter_runtime_matrix import build_matrix, render_markdown


def contract_fixture():
    return {
        "schema": "harness.cross-harness-adapter-contract/v1",
        "provider_roles": [
            {
                "provider_role": "codex_harness",
                "harness_id": "codex",
                "target_model": "5.3-Codex-Spark",
                "adapter_state": "contract_only",
                "allowed_modes": ["manifest_only", "focused_run_after_approval"],
                "required_receipts": ["raw_prompt", "raw_output"],
            },
            {
                "provider_role": "claude_code",
                "harness_id": "claude_code",
                "target_model": "configured_by_operator",
                "adapter_state": "needs_discovery",
                "allowed_modes": ["manifest_only", "focused_run_after_approval"],
                "required_receipts": ["raw_prompt", "raw_output"],
            },
            {
                "provider_role": "local_14b",
                "harness_id": "local_endpoint",
                "target_model": "14B",
                "adapter_state": "needs_endpoint_profile_and_gate",
                "allowed_modes": ["manifest_only", "endpoint_profile", "focused_run_after_approval"],
                "required_receipts": ["endpoint_profile", "endpoint_gate"],
            },
        ],
    }


def endpoint_profiles_fixture():
    return {
        "schema": "harness.model-endpoint-profiles/v1",
        "profiles": [
            {
                "profile_id": "serve-14b",
                "model": "14B",
                "backend": "serve",
                "provider_role": "flywheel",
                "root_exists": True,
                "supports_agentic_workflow": True,
                "live_probed": False,
            }
        ],
    }


def auth_fixture():
    return {
        "schema": "harness.endpoint-auth-status/v1",
        "lanes": [
            {"id": "codex_subscription", "provider": "codex", "mode": "plan", "kind": "subscription_cli", "configured": True},
            {"id": "claude_subscription", "provider": "claude", "mode": "plan", "kind": "subscription_cli", "configured": False},
        ],
    }


def test_build_matrix_joins_contract_endpoint_profiles_and_auth_status():
    matrix = build_matrix(
        contract_fixture(),
        contract_path="contract.json",
        contract_sha256="abc123",
        endpoint_profiles=endpoint_profiles_fixture(),
        endpoint_auth_status=auth_fixture(),
        run_id="run_123",
    )

    assert matrix["schema"] == "harness.adapter-runtime-matrix/v1"
    assert matrix["summary"]["runtime_rows"] == 3
    assert matrix["summary"]["provider_execution"] is False
    assert matrix["summary"]["endpoint_probe"] is False
    assert matrix["summary"]["model_weight_read"] is False
    assert matrix["summary"]["token_store_read"] is False
    codex = [row for row in matrix["runtime_rows"] if row["provider_role"] == "codex_harness"][0]
    local = [row for row in matrix["runtime_rows"] if row["provider_role"] == "local_14b"][0]
    claude = [row for row in matrix["runtime_rows"] if row["provider_role"] == "claude_code"][0]
    assert codex["auth_ready"] is True
    assert local["endpoint_profile_ready"] is True
    assert "endpoint_gate" in local["blocking_gates"]
    assert "adapter_discovery" in claude["blocking_gates"]
    assert "account_auth" in claude["blocking_gates"]
    json.dumps(matrix)


def test_render_markdown_lists_roles_and_non_execution_guards():
    matrix = build_matrix(
        contract_fixture(),
        contract_path="contract.json",
        contract_sha256="abc123",
        endpoint_profiles=endpoint_profiles_fixture(),
        endpoint_auth_status=auth_fixture(),
    )

    markdown = render_markdown(matrix)

    assert "# Adapter runtime matrix" in markdown
    assert "codex_harness" in markdown
    assert "local_14b" in markdown
    assert "must not call Codex" in markdown
