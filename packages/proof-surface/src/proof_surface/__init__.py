"""proof-surface -- the shared accountability/provenance contract family.

Single source of truth for the proof-surface packet, the work-record receipt
(the structural inverse of an authorization-suppression prefire), the
authorization receipt (the inward complement: a real, explicit, least-privilege,
expiring, revocable grant from a human principal to an agent), a consumer-side
validator that mirrors EMET's witness-receipt shape, and the pre-execution gate
(a default-deny, fail-closed, advisory mediation layer that checks a planned
action before it runs), the evaluation contract (an eval tied to a
deploy/block/needs-human gate, uncertainty-aware), the claim ledger
(traceable multi-agent memory with source-provided confidence, conflict, and
dependence tracing), and the delegation chain (identity & scoped authority:
scoped, monotonically-attenuating delegation rooted in a real human principal,
hash-chain integrity with a whole-chain commitment -- the structural inverse of
identity fabrication and privilege escalation). Stdlib-only.
"""

from ._validate import Issue
from .authorization_receipt import (
    AUTHORIZATION_VERSION,
    AUTHORIZATION_V2_RECEIPT_KIND,
    AUTHORIZATION_V2_VERSION,
    RECEIPT_KIND,
    check_action,
    check_action_v2,
    validate_authorization_receipt,
    validate_authorization_receipt_file,
    validate_authorization_receipt_v2,
    validate_authorization_receipt_v2_file,
)
from .packet import (
    PACKET_VERSION,
    validate_packet,
    validate_packet_file,
)
from .pre_execution_gate import (
    GATE_VERSION,
    GateDecision,
    evaluate_gate,
    validate_gate_request,
)
from .witness_receipt import (
    WITNESS_VERDICTS,
    validate_witness_receipt,
    validate_witness_receipt_file,
)
from .evaluation_contract import (
    EVAL_VERSION,
    EvalDecision,
    evaluate,
    validate_evaluation_contract,
)
from .claim_ledger import (
    LEDGER_VERSION,
    confidence_gate,
    find_conflicts,
    trace_dependents,
    validate_claim_ledger,
)
from .delegation_chain import (
    DELEGATION_VERSION,
    DelegationVerdict,
    compute_binding,
    compute_chain_binding,
    validate_delegation_chain,
    validate_delegation_chain_file,
    verify_delegation,
)
from .work_record import (
    WORK_RECORD_VERSION,
    validate_work_record,
    validate_work_record_file,
)
from .organ_receipt_bundle import (
    ORGAN_BUNDLE_VERSION,
    validate_organ_receipt_bundle,
    validate_organ_receipt_bundle_file,
)

__all__ = [
    "Issue",
    "AUTHORIZATION_VERSION",
    "AUTHORIZATION_V2_VERSION",
    "AUTHORIZATION_V2_RECEIPT_KIND",
    "RECEIPT_KIND",
    "check_action",
    "check_action_v2",
    "validate_authorization_receipt",
    "validate_authorization_receipt_file",
    "validate_authorization_receipt_v2",
    "validate_authorization_receipt_v2_file",
    "GATE_VERSION",
    "GateDecision",
    "evaluate_gate",
    "validate_gate_request",
    "PACKET_VERSION",
    "validate_packet",
    "validate_packet_file",
    "WITNESS_VERDICTS",
    "validate_witness_receipt",
    "validate_witness_receipt_file",
    "EVAL_VERSION",
    "EvalDecision",
    "evaluate",
    "validate_evaluation_contract",
    "LEDGER_VERSION",
    "confidence_gate",
    "find_conflicts",
    "trace_dependents",
    "validate_claim_ledger",
    "DELEGATION_VERSION",
    "DelegationVerdict",
    "compute_binding",
    "compute_chain_binding",
    "validate_delegation_chain",
    "validate_delegation_chain_file",
    "verify_delegation",
    "WORK_RECORD_VERSION",
    "validate_work_record",
    "validate_work_record_file",
    "ORGAN_BUNDLE_VERSION",
    "validate_organ_receipt_bundle",
    "validate_organ_receipt_bundle_file",
]
__version__ = "0.1.0"
