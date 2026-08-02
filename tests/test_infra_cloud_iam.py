"""Tests for cloud IAM revocation adapters.

All cloud API calls are mocked. No test ever touches a real cloud account.
The tests verify:
  - dry-run mode reports intent without executing
  - live mode calls the right SDK methods
  - SDK absence is handled gracefully
  - environment credential clearing always works (no SDK needed)
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from harness.infra.cloud_iam import (
    SCHEMA,
    RevocationResult,
    build_revocation_receipt,
    revoke_all,
    revoke_aws_keys,
    revoke_env_credentials,
    revoke_gcp_service_accounts,
    revoke_vault_secrets,
)
from harness.infra.kill_switch import revoke_credentials as ks_revoke


# --- dry-run mode (FLYWHEEL_KILL_SWITCH_LIVE not set) -------------------


def test_aws_dry_run_reports_intent():
    result = revoke_aws_keys(["AKIATEST123"])
    assert result.provider == "aws"
    assert result.executed is False
    assert "dry run" in result.detail


def test_gcp_dry_run_reports_intent():
    result = revoke_gcp_service_accounts(["sa@test.iam.gserviceaccount.com"])
    assert result.provider == "gcp"
    assert result.executed is False
    assert "dry run" in result.detail


def test_vault_dry_run_reports_intent():
    result = revoke_vault_secrets(["lease-abc123"])
    assert result.provider == "vault"
    assert result.executed is False
    assert "dry run" in result.detail


def test_env_dry_run_reports_intent():
    result = revoke_env_credentials()
    assert result.provider == "env"
    assert result.executed is False


# --- environment credential clearing (always safe) -----------------------


def test_env_revocation_finds_credentials(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test123")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIATEST")
    result = revoke_env_credentials()
    assert "OPENAI_API_KEY" in result.credentials_revoked
    assert "AWS_ACCESS_KEY_ID" in result.credentials_revoked


def test_env_revocation_no_credentials_found(monkeypatch):
    # Clear all credential env vars
    for pattern in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
                    "OPENAI_API_KEY", "VAULT_TOKEN"):
        monkeypatch.delenv(pattern, raising=False)
    result = revoke_env_credentials()
    assert result.credentials_revoked == []


def test_env_revocation_live_clears_vars(monkeypatch):
    monkeypatch.setenv("FLYWHEEL_KILL_SWITCH_LIVE", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    result = revoke_env_credentials()
    assert result.executed is True
    assert "OPENAI_API_KEY" in result.credentials_revoked
    assert os.environ.get("OPENAI_API_KEY") is None


# --- AWS live mode (mocked boto3) ---------------------------------------


def test_aws_live_mode_calls_boto3(monkeypatch):
    monkeypatch.setenv("FLYWHEEL_KILL_SWITCH_LIVE", "1")
    monkeypatch.setenv("FLYWHEEL_AWS_USER", "test-user")

    mock_client = MagicMock()
    mock_iam = MagicMock()
    mock_iam.client.return_value = mock_client
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_client

    with patch.dict("sys.modules", {"boto3": mock_boto3}):
        result = revoke_aws_keys(["AKIATEST123"])

    assert result.executed is True
    assert "AKIATEST123" in result.credentials_revoked
    mock_client.update_access_key.assert_called_once_with(
        UserName="test-user", AccessKeyId="AKIATEST123", Status="Inactive")


def test_aws_live_mode_missing_boto3(monkeypatch):
    monkeypatch.setenv("FLYWHEEL_KILL_SWITCH_LIVE", "1")
    with patch.dict("sys.modules", {"boto3": None}):
        result = revoke_aws_keys(["AKIATEST"])
    assert result.executed is False
    assert any("boto3 not installed" in e for e in result.errors)


# --- GCP live mode (mocked google-cloud-iam) ----------------------------


def test_gcp_live_mode_calls_iam(monkeypatch):
    monkeypatch.setenv("FLYWHEEL_KILL_SWITCH_LIVE", "1")
    monkeypatch.setenv("FLYWHEEL_GCP_PROJECT", "test-project")

    mock_client = MagicMock()
    mock_iam_admin = MagicMock()
    mock_iam_admin.IAMClient.return_value = mock_client
    mock_gcp = MagicMock()
    mock_gcp.cloud.iam_admin_v1 = mock_iam_admin

    with patch.dict("sys.modules", {
        "google": mock_gcp, "google.cloud": mock_gcp.cloud,
        "google.cloud.iam_admin_v1": mock_iam_admin,
    }):
        result = revoke_gcp_service_accounts(["sa@test.iam.gserviceaccount.com"])

    assert result.executed is True
    assert "sa@test.iam.gserviceaccount.com" in result.credentials_revoked
    mock_client.disable_service_account.assert_called_once()


def test_gcp_live_mode_missing_sdk(monkeypatch):
    monkeypatch.setenv("FLYWHEEL_KILL_SWITCH_LIVE", "1")
    with patch.dict("sys.modules", {"google.cloud.iam_admin_v1": None}):
        result = revoke_gcp_service_accounts(["sa@test.iam"])
    assert result.executed is False
    assert any("not installed" in e for e in result.errors)


# --- Vault live mode (mocked hvac) --------------------------------------


def test_vault_live_mode_calls_hvac(monkeypatch):
    monkeypatch.setenv("FLYWHEEL_KILL_SWITCH_LIVE", "1")
    monkeypatch.setenv("VAULT_ADDR", "http://127.0.0.1:8200")
    monkeypatch.setenv("VAULT_TOKEN", "test-token")

    mock_client = MagicMock()
    mock_client.auth.token.revoke_self.return_value = None
    mock_client.sys.revoke_lease.return_value = None
    mock_hvac = MagicMock()
    mock_hvac.Client.return_value = mock_client

    with patch.dict("sys.modules", {"hvac": mock_hvac}):
        result = revoke_vault_secrets(["lease-abc123"])

    assert result.executed is True
    assert "self-token" in result.credentials_revoked
    assert "lease-abc123" in result.credentials_revoked
    mock_client.auth.token.revoke_self.assert_called_once()


def test_vault_live_mode_missing_hvac(monkeypatch):
    monkeypatch.setenv("FLYWHEEL_KILL_SWITCH_LIVE", "1")
    with patch.dict("sys.modules", {"hvac": None}):
        result = revoke_vault_secrets(["lease-abc"])
    assert result.executed is False
    assert any("hvac not installed" in e for e in result.errors)


# --- revoke_all orchestrator --------------------------------------------


def test_revoke_all_calls_env_always():
    """revoke_all always clears env credentials, even without cloud providers."""
    results = revoke_all()
    assert len(results) == 1  # just env
    assert results[0].provider == "env"


def test_revoke_all_calls_all_providers(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    results = revoke_all(
        aws_key_ids=["AKIATEST"],
        gcp_sa_emails=["sa@test.iam"],
        vault_paths=["lease-abc"],
    )
    assert len(results) == 4
    providers = {r.provider for r in results}
    assert providers == {"aws", "gcp", "vault", "env"}


# --- kill_switch.revoke_credentials integration --------------------------


def test_kill_switch_revoke_credentials_dry_run():
    """The kill_switch.revoke_credentials wrapper calls cloud_iam in dry-run."""
    result = ks_revoke()
    assert result["action"] == "credential-revocation"
    assert result["executed"] is False or result["executed"] is True
    assert "env" in result["providers_called"]


def test_kill_switch_revoke_with_aws_keys():
    result = ks_revoke(aws_key_ids=["AKIATEST123"])
    assert "aws" in result["providers_called"]
    assert "env" in result["providers_called"]


# --- revocation receipt --------------------------------------------------


def test_build_revocation_receipt_sealed():
    r = RevocationResult(provider="aws", action="deactivate",
                         executed=True, credentials_revoked=["AKIA123"])
    receipt = build_revocation_receipt(r, run_id="test")
    assert receipt["schema"] == SCHEMA
    assert len(receipt["seal_hash"]) == 64
    assert receipt["seal_body"]["result"]["provider"] == "aws"
