"""infra_route.py -- the infrastructure controls, reachable at last.

Six routes over `harness/infra/`. Three read: the trust model and its single
points of failure, the run bill of materials, and the live egress table
classified against the allowlist. Three act, and each one arrives through a
grant: a credential scan that reads where secrets live, a boundary probe that
leaves the machine, and the kill switch.

Every answer here is the module's own sealed receipt. Nothing on this path
recomputes a verdict or composes a second summary over one the engine already
sealed; the seal is what makes the answer re-checkable later.
"""
from __future__ import annotations

from pathlib import Path

READ_PATHS = ("/api/infra/trust-model", "/api/infra/bom", "/api/infra/egress")
ACT_PATHS = ("/api/infra/credential-scan", "/api/infra/isolation",
             "/api/infra/kill")


def handle_infra_get(path: str) -> tuple[dict, int]:
    if path == "/api/infra/trust-model":
        from harness.infra.trust_model import default_flywheel_trust_model
        model = default_flywheel_trust_model()
        body = model.to_dict()
        # The model states its own single points of failure; the derived list
        # is what the components actually imply. A gap between the two is the
        # finding, so both are shown rather than one silently winning.
        derived = model.find_single_points_of_failure()
        body["derived_single_points_of_failure"] = derived
        body["validation_errors"] = model.validate()
        # The comparison is made here, once, so no surface has to make it a
        # second time and reach a different answer.
        body["single_point_agreement"] = (
            sorted(body.get("single_points_of_failure") or []) == sorted(derived))
        return body, 200
    if path == "/api/infra/bom":
        from harness.infra.run_bom import default_flywheel_bom
        return default_flywheel_bom().sealed(), 200
    if path == "/api/infra/egress":
        from harness.infra.egress import scan_egress
        from harness.infra.egress_matrix import default_matrix
        matrix = default_matrix()
        receipts = scan_egress(matrix, run_id="gateway-egress")
        # An empty list is an honest null and reads as one: either nothing is
        # connected, or psutil is absent and the socket table is unreadable.
        # The tally is made here so no surface has to count a second time.
        counts: dict[str, int] = {}
        for receipt in receipts:
            verdict = receipt.get("seal_body", {}).get("verdict", "UNKNOWN")
            counts[verdict] = counts.get(verdict, 0) + 1
        return {"matrix": matrix.to_dict(), "receipts": receipts,
                "count": len(receipts), "verdict_counts": counts,
                "reason": "" if receipts else
                          "no classifiable connection was readable"}, 200
    return {"error": "not found"}, 404


def handle_infra_post(path: str, req: object) -> tuple[dict, int]:
    body = req if isinstance(req, dict) else {}
    if path == "/api/infra/credential-scan":
        return _credential_scan(body)
    if path == "/api/infra/isolation":
        from harness.infra.isolation_test import run_isolation_test
        return run_isolation_test(run_id="gateway-isolation"), 200
    if path == "/api/infra/kill":
        return _kill(body)
    return {"error": "not found"}, 404


def _credential_scan(body: dict) -> tuple[dict, int]:
    from harness.infra.credential_scanner import (
        build_credential_scan_receipt, scan_all)
    raw = body.get("root")
    root: Path | None = None
    if isinstance(raw, str) and raw.strip():
        root = Path(raw)
        if not root.is_dir():
            return {"error": "root is not a directory that exists"}, 400
    findings = scan_all(root)
    receipt = build_credential_scan_receipt(
        findings=findings, scan_root=str(root) if root else "",
        run_id="gateway-credscan")
    # The findings carry a fingerprint and a location. They never carry the
    # value, and the receipt this route returns is the receipt the scanner
    # sealed, so what the operator reads is what verifies.
    return receipt, 200


def _kill(body: dict) -> tuple[dict, int]:
    from harness.infra.kill_switch import (
        ACTIONS, KillRequest, build_kill_receipt, isolate_network,
        revoke_credentials, terminate_process)
    wanted = body.get("actions")
    request = KillRequest(
        run_id="gateway-kill", reason=str(body.get("reason", "")),
        mode=str(body.get("mode") or "evidence-preserving"),
        actions=list(wanted) if isinstance(wanted, list) and wanted
        else list(ACTIONS))
    request.add_authority(str(body.get("authority_1", "")))
    request.add_authority(str(body.get("authority_2", "")))
    if not request.confirmed:
        # Two authorities, and they must differ. An unconfirmed request is a
        # receipt of the refusal, which is why it is still a 200: the operator
        # asked, the switch said no, and that exchange is the record.
        return build_kill_receipt(request), 200
    results = [_run_kill_action(name, isolate_network, revoke_credentials,
                                terminate_process)
               for name in request.actions]
    receipt = build_kill_receipt(request)
    receipt["action_results"] = results
    receipt["any_executed"] = any(r.get("executed") for r in results)
    return receipt, 200


def _run_kill_action(name: str, isolate, revoke, terminate) -> dict:
    """Run one kill action, or say plainly that this build cannot run it.

    The switch is safe by default: without FLYWHEEL_KILL_SWITCH_LIVE every
    action reports executed False and says why. Reporting anything else would
    fabricate a safety action that never happened."""
    if name == "network-isolation":
        return isolate()
    if name == "credential-revocation":
        return revoke()
    if name == "process-termination":
        return terminate()
    return {"action": name, "executed": False,
            "reason": "no backend is wired for this action"}
