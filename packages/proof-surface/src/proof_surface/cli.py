"""Unified `telos proof <domain>` dispatcher.

One buyer-facing seam over the proof-packet family: pick a domain, get the same
mental model. Each domain owns its own arguments; this only routes.

    telos-proof agent-action       --trace ... --authorization ... --claim ...
    telos-proof visual-measurement --input ... --claim ...
    telos-proof research-claim     --input ... --claim ...
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

from ._bundle import verify_receipts
from ._strict_json import strict_json_load
from .authorization_receipt import (
    validate_authorization_receipt,
    validate_authorization_receipt_v2,
)
from .organ_receipt_bundle import validate_organ_receipt_bundle

_DOMAINS = {
    "agent-action": "proof_surface.agent_action.cli",
    "visual-measurement": "proof_surface.visual_measurement.cli",
    "research-claim": "proof_surface.research_claim.cli",
    "model-eval": "proof_surface.model_eval.cli",
    "optimization-workflow": "proof_surface.optimization_workflow.cli",
    "rollout-receipt": "proof_surface.rollout_receipt.cli",
    "eval-attempt": "proof_surface.eval_attempt.cli",
    "ai4science": "proof_surface.ai4science.cli",
    "conservation": "proof_surface.conservation.cli",
    "control-certificate": "proof_surface.control_certificate.cli",
    "competition-attempt": "proof_surface.competition_attempt.cli",
}


def _usage() -> str:
    domains = "\n".join(f"    telos-proof {name} ..." for name in sorted(_DOMAINS))
    return (
        "usage: telos-proof <domain> [options]\n"
        "       telos-proof validate <document.json>\n"
        "       telos-proof verify <artifact-dir>\n\n"
        "domains:\n" + domains
    )


def _validation_result(path: Path) -> tuple[int, dict]:
    try:
        document = strict_json_load(path)
    except (FileNotFoundError, OSError, UnicodeError, ValueError) as exc:
        return 2, {
            "verdict": "UNVERIFIABLE",
            "reason": "malformed_document",
            "issues": [{"path": "$", "message": str(exc)}],
        }

    if not isinstance(document, dict):
        return 2, {
            "verdict": "UNVERIFIABLE",
            "reason": "unknown_contract",
            "issues": [{"path": "$", "message": "expected object"}],
        }

    contract: str
    if document.get("organ_bundle_version") == "0.1":
        contract = "organ-receipt-bundle/v0.1"
        issues = validate_organ_receipt_bundle(document)
    elif document.get("authorization_version") == "0.1":
        contract = "authorization-receipt/v0.1"
        issues = validate_authorization_receipt(document)
    elif document.get("authorization_version") == "0.2":
        contract = "authorization-receipt/v0.2"
        issues = validate_authorization_receipt_v2(document)
    else:
        return 2, {
            "verdict": "UNVERIFIABLE",
            "reason": "unknown_contract",
            "issues": [],
        }

    return (1 if issues else 0), {
        "contract": contract,
        "verdict": "UNVERIFIABLE" if issues else "MATCH",
        "issues": [
            {"path": issue.path, "message": issue.message} for issue in issues
        ],
    }


def _verify_result(directory: Path) -> tuple[int, dict]:
    issues = verify_receipts(directory)
    payload = [{"path": issue.path, "message": issue.message} for issue in issues]
    if any(issue.path == "$.bundle.json" for issue in issues):
        return 2, {"verdict": "UNVERIFIABLE", "reason": "no_manifest", "issues": payload}
    if issues:
        return 1, {"verdict": "DRIFT", "issues": payload}
    return 0, {"verdict": "MATCH", "issues": payload}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv:
        print(_usage(), file=sys.stderr)
        return 2
    if argv[0] in ("-h", "--help"):
        print(_usage())
        return 0

    if argv[0] == "validate":
        if len(argv) != 2:
            print(
                json.dumps(
                    {
                        "verdict": "UNVERIFIABLE",
                        "reason": "usage",
                        "issues": [],
                    },
                    sort_keys=True,
                )
            )
            return 2
        exit_code, result = _validation_result(Path(argv[1]))
        print(json.dumps(result, sort_keys=True))
        return exit_code

    if argv[0] == "verify":
        if len(argv) != 2:
            print(
                json.dumps(
                    {"verdict": "UNVERIFIABLE", "reason": "usage", "issues": []},
                    sort_keys=True,
                )
            )
            return 2
        exit_code, result = _verify_result(Path(argv[1]))
        print(json.dumps(result, sort_keys=True))
        return exit_code

    domain = argv[0]
    if domain not in _DOMAINS:
        print(f"error: unknown domain {domain!r}\n\n{_usage()}", file=sys.stderr)
        return 2

    module = importlib.import_module(_DOMAINS[domain])
    return module.main(argv[1:])


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
