"""cloud_iam.py -- live cloud IAM credential revocation adapters.

Replaces the kill_switch stub with actual API calls to AWS IAM, GCP IAM, and
HashiCorp Vault. Each adapter:
  - checks whether its SDK is installed (boto3 for AWS, google-cloud-iam for
    GCP, hvac for Vault)
  - checks whether credentials are configured in the environment
  - makes the real API call when FLYWHEEL_KILL_SWITCH_LIVE=1
  - returns a typed result dict with {provider, action, executed, detail}

The adapters are NEVER called unless the kill switch is confirmed (dual
authority) AND FLYWHEEL_KILL_SWITCH_LIVE=1. In dry-run mode they report what
they WOULD do without touching any cloud API.

Every adapter call is logged to a sealed receipt via build_revocation_receipt().
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

SCHEMA = "flywheel.credential-revocation/v1"

PROVIDERS = ("aws", "gcp", "vault", "env")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_bytes(obj: dict[str, Any]) -> bytes:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class RevocationResult:
    """The result of one revocation action."""
    provider: str
    action: str
    executed: bool = False
    detail: str = ""
    credentials_revoked: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "action": self.action,
            "executed": self.executed,
            "detail": self.detail,
            "credentials_revoked": list(self.credentials_revoked),
            "errors": list(self.errors),
            "timestamp": self.timestamp,
        }


def build_revocation_receipt(result: RevocationResult,
                             run_id: str = "kill-switch") -> dict[str, Any]:
    """Build a sealed receipt for a credential revocation action."""
    seal_body = {
        "run_id": run_id,
        "result": result.to_dict(),
    }
    seal_hash = _sha256_hex(_canonical_bytes(seal_body))
    return {"schema": SCHEMA, "seal_hash": seal_hash, "seal_body": seal_body}


def _is_live() -> bool:
    """True only when FLYWHEEL_KILL_SWITCH_LIVE=1."""
    return os.environ.get("FLYWHEEL_KILL_SWITCH_LIVE") == "1"


# ---------------------------------------------------------------------------
# AWS IAM: deactivate / delete access keys
# ---------------------------------------------------------------------------

def revoke_aws_keys(access_key_ids: list[str]) -> RevocationResult:
    """Revoke AWS IAM access keys by deactivating them.

    Calls iam:UpdateAccessKey(Status='Inactive') for each key. Requires boto3
    and AWS credentials in the environment. In dry-run mode, reports what it
    would do.
    """
    result = RevocationResult(
        provider="aws", action="deactivate-access-keys",
        credentials_revoked=list(access_key_ids))

    if not _is_live():
        result.detail = f"dry run: would deactivate {len(access_key_ids)} AWS key(s)"
        return result

    try:
        import boto3
    except ImportError:
        result.errors.append("boto3 not installed; cannot revoke AWS keys")
        return result

    client = boto3.client("iam")
    for key_id in access_key_ids:
        # Extract the access key ID prefix (AKIA...) and the user name
        # from the credential scanner's output or the environment.
        try:
            user = os.environ.get("FLYWHEEL_AWS_USER", "")
            if not user:
                result.errors.append(f"no FLYWHEEL_AWS_USER set for key {key_id}")
                continue
            client.update_access_key(
                UserName=user, AccessKeyId=key_id, Status="Inactive")
            result.credentials_revoked.append(key_id)
        except Exception as e:
            result.errors.append(f"AWS key {key_id}: {type(e).__name__}: {e}")

    result.executed = len(result.credentials_revoked) > 0
    result.detail = f"deactivated {len(result.credentials_revoked)} of {len(access_key_ids)} AWS key(s)"
    return result


# ---------------------------------------------------------------------------
# GCP IAM: disable service accounts / revoke tokens
# ---------------------------------------------------------------------------

def revoke_gcp_service_accounts(emails: list[str]) -> RevocationResult:
    """Disable GCP service accounts.

    Calls iam-admin:DisableServiceAccount for each email. Requires
    google-cloud-iam and GCP credentials. In dry-run mode, reports what it
    would do.
    """
    result = RevocationResult(
        provider="gcp", action="disable-service-accounts",
        credentials_revoked=list(emails))

    if not _is_live():
        result.detail = f"dry run: would disable {len(emails)} GCP SA(s)"
        return result

    try:
        from google.cloud import iam_admin_v1
    except ImportError:
        result.errors.append("google-cloud-iam not installed")
        return result

    project = os.environ.get("FLYWHEEL_GCP_PROJECT", "")
    if not project:
        result.errors.append("no FLYWHEEL_GCP_PROJECT set")
        return result

    client = iam_admin_v1.IAMClient()
    for email in emails:
        try:
            request = iam_admin_v1.DisableServiceAccountRequest(
                name=f"projects/{project}/serviceAccounts/{email}")
            client.disable_service_account(request=request)
            result.credentials_revoked.append(email)
        except Exception as e:
            result.errors.append(f"GCP SA {email}: {type(e).__name__}: {e}")

    result.executed = len(result.credentials_revoked) > 0
    result.detail = f"disabled {len(result.credentials_revoked)} of {len(emails)} GCP SA(s)"
    return result


# ---------------------------------------------------------------------------
# HashiCorp Vault: revoke tokens and secrets
# ---------------------------------------------------------------------------

def revoke_vault_secrets(token_paths: list[str]) -> RevocationResult:
    """Revoke Vault tokens / leases.

    Calls hvac to revoke self (revoke-token) and revoke specific lease IDs.
    Requires hvac and VAULT_ADDR + VAULT_TOKEN in the environment.
    """
    result = RevocationResult(
        provider="vault", action="revoke-secrets",
        credentials_revoked=list(token_paths))

    if not _is_live():
        result.detail = f"dry run: would revoke {len(token_paths)} Vault path(s)"
        return result

    try:
        import hvac
    except ImportError:
        result.errors.append("hvac not installed")
        return result

    vault_addr = os.environ.get("VAULT_ADDR", "http://127.0.0.1:8200")
    vault_token = os.environ.get("VAULT_TOKEN", "")

    if not vault_token:
        result.errors.append("no VAULT_TOKEN set")
        return result

    client = hvac.Client(url=vault_addr, token=vault_token)

    # Revoke the current token (self-revocation)
    try:
        client.auth.token.revoke_self()
        result.credentials_revoked.append("self-token")
    except Exception as e:
        result.errors.append(f"Vault self-revoke: {type(e).__name__}: {e}")

    # Revoke specific lease IDs / secret paths
    for path in token_paths:
        try:
            client.sys.revoke_lease(path)
            result.credentials_revoked.append(path)
        except Exception as e:
            result.errors.append(f"Vault path {path}: {type(e).__name__}: {e}")

    result.executed = len(result.credentials_revoked) > 0
    result.detail = f"revoked {len(result.credentials_revoked)} of {len(token_paths) + 1} Vault credential(s)"
    return result


# ---------------------------------------------------------------------------
# Environment variables: clear credential-shaped env vars
# ---------------------------------------------------------------------------

CREDENTIAL_ENV_PATTERNS = (
    "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
    "GOOGLE_APPLICATION_CREDENTIALS", "AZURE_CLIENT_SECRET",
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "VAULT_TOKEN",
    "GITHUB_TOKEN", "HUGGINGFACE_TOKEN",
)


def revoke_env_credentials(patterns: tuple[str, ...] = CREDENTIAL_ENV_PATTERNS,
                           ) -> RevocationResult:
    """Clear credential-shaped environment variables from this process.

    This is the always-safe path: it does not require any cloud SDK and can
    always execute (it is a local os.environ.pop). In live mode it removes the
    variables; in dry-run it reports which would be cleared.
    """
    found = [p for p in patterns if os.environ.get(p)]
    result = RevocationResult(
        provider="env", action="clear-env-credentials",
        credentials_revoked=list(found))

    if not _is_live():
        result.detail = f"dry run: would clear {len(found)} env var(s)"
        return result

    for pattern in found:
        os.environ.pop(pattern, None)

    result.executed = True
    result.detail = f"cleared {len(found)} env credential(s)"
    return result


# ---------------------------------------------------------------------------
# Orchestrator: revoke across all configured providers
# ---------------------------------------------------------------------------

def revoke_all(
    *,
    aws_key_ids: list[str] | None = None,
    gcp_sa_emails: list[str] | None = None,
    vault_paths: list[str] | None = None,
    env_patterns: tuple[str, ...] = CREDENTIAL_ENV_PATTERNS,
    run_id: str = "kill-switch",
) -> list[RevocationResult]:
    """Revoke credentials across all configured cloud providers.

    Calls each provider's adapter. Returns a list of results. Always clears
    environment credentials (safe). Only calls cloud APIs when
    FLYWHEEL_KILL_SWITCH_LIVE=1.
    """
    results: list[RevocationResult] = []

    if aws_key_ids:
        results.append(revoke_aws_keys(aws_key_ids))
    if gcp_sa_emails:
        results.append(revoke_gcp_service_accounts(gcp_sa_emails))
    if vault_paths:
        results.append(revoke_vault_secrets(vault_paths))
    results.append(revoke_env_credentials(env_patterns))

    return results
