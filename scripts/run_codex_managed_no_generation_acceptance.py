"""No-generation managed Codex account/config/restart acceptance probe.

The runner requires an owner-supplied existing managed profile. It does not
initiate login, copy ambient credentials, start provider turns, or answer tool
approvals.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from harness.codex_managed_inventory_lifecycle import CodexManagedInventoryLifecycle
from scripts.codex_managed_acceptance_support import (
    AcceptanceConfig,
    AcceptanceError,
    SCHEMA,
    add_assertion,
    base_receipt,
    dt_now,
    pass_if,
    preflight_roots,
    probe,
    probe_summary,
    safe_owner,
    write_json,
)


def run_acceptance(
        cfg: AcceptanceConfig, *,
        lifecycle_factory=CodexManagedInventoryLifecycle,
        clock=None) -> dict[str, Any]:
    clock = clock or dt_now
    owner = safe_owner(cfg.owner_ref)
    receipt = base_receipt(REPO_ROOT, cfg, owner, clock())
    lifecycle = None
    try:
        roots = preflight_roots(cfg, receipt, owner)
        lifecycle = lifecycle_factory(
            state_root=roots["state_root"], policy_root=roots["policy_root"],
            workspace=roots["workspace"], executable=roots["executable"],
            executable_sha256=cfg.executable_sha256.lower(),
            configured_version=cfg.codex_version,
            version_provenance=cfg.version_provenance, model=cfg.model)
        first = _run_probe_assertion(receipt, lifecycle, owner, cfg.model,
                                     "first", "P07_first_no_generation_probe")
        receipt["probes"] = [first]
        if first.get("error"):
            receipt["error"] = "probe_failed_" + first["error"]
        else:
            second = _run_probe_assertion(receipt, lifecycle, owner, cfg.model,
                                          "restart", "P08_restart_no_generation_probe")
            receipt["probes"].append(second)
            receipt["restart"] = {
                "inventory_sha256_match": first.get("inventory_sha256") == second.get("inventory_sha256"),
                "config_digest_match": first.get("config_digest") == second.get("config_digest"),
            }
            add_assertion(receipt, "P09_restart_binding_stable",
                          pass_if(all(receipt["restart"].values())), receipt["restart"])
            if second.get("error"):
                receipt["error"] = "probe_failed_" + second["error"]
    except AcceptanceError as exc:
        receipt["error"] = exc.code
        receipt.update(exc.detail)
    except Exception as exc:
        receipt["error"] = type(exc).__name__
    finally:
        _record_cleanup(receipt, lifecycle)
    receipt["complete"] = (
        not receipt.get("error")
        and all(row["state"] == "PASS" for row in receipt["assertions"]))
    receipt["ended_utc"] = clock()
    write_json(cfg.out, receipt)
    return receipt


def _run_probe_assertion(receipt: dict, lifecycle, owner: str, model: str,
                         phase: str, assertion_id: str) -> dict[str, Any]:
    row = probe(lifecycle, owner, model, phase)
    summary = probe_summary(row)
    state = pass_if(all(summary.values()) and not row.get("error"))
    add_assertion(receipt, assertion_id, state, summary)
    if row.get("cleanup", {}).get("reason") == "AGENT_NATIVE_CLEANUP_REQUIRED":
        receipt["cleanup"] = row["cleanup"]
    return row


def _record_cleanup(receipt: dict, lifecycle) -> None:
    existing = dict(receipt.get("cleanup") or {})
    lifecycle_ok = True
    if lifecycle is not None:
        try:
            lifecycle_ok = lifecycle.shutdown() is True
        except Exception:
            lifecycle_ok = False
    cleanup = {**existing, "lifecycle_shutdown": lifecycle_ok}
    if existing.get("reason") == "AGENT_NATIVE_CLEANUP_REQUIRED" or not lifecycle_ok:
        cleanup["reason"] = "AGENT_NATIVE_CLEANUP_REQUIRED"
    receipt["cleanup"] = cleanup
    if lifecycle is not None:
        add_assertion(receipt, "P10_cleanup_complete",
                      pass_if(cleanup.get("reason") != "AGENT_NATIVE_CLEANUP_REQUIRED"), cleanup)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner-ref", required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--policy-root", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--profile-home", type=Path, required=True)
    parser.add_argument("--codex-executable", type=Path, required=True)
    parser.add_argument("--codex-executable-sha256", required=True)
    parser.add_argument("--codex-version", required=True)
    parser.add_argument("--version-provenance", default="configured")
    parser.add_argument("--model", required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    receipt = run_acceptance(AcceptanceConfig(
        owner_ref=args.owner_ref, state_root=args.state_root,
        policy_root=args.policy_root, workspace=args.workspace,
        profile_home=args.profile_home, executable=args.codex_executable,
        executable_sha256=args.codex_executable_sha256,
        codex_version=args.codex_version,
        version_provenance=args.version_provenance, model=args.model,
        out=args.out))
    print(json.dumps({"schema": SCHEMA + "-summary",
                      "complete": receipt["complete"], "out": str(args.out)}))
    return 0 if receipt.get("complete") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
