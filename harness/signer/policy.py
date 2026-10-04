"""policy.py -- the machine policy check, run inside the signer.

A rule counts as ``policy:machine`` only when code outside the agent checked
it. The signer is that code once it runs under its own identity, so it
evaluates the pre-action rule pack itself and signs the result:

  * the rule pack is the one installed beside the signer, never one the caller
    sends;
  * the run context (workspace, allowed hosts, protected paths) comes from
    ``policy-context.json`` in the signer's home, which the operator writes and
    the agent cannot. With no such file the context is empty, which is the
    strictest: no host is allowed and no workspace is trusted;
  * the caller supplies only the call (tool, arguments, path id). The signed
    statement carries the argument digest in the same form the tool-call
    receipt uses, so a verifier can check the statement covers the call the
    receipt records.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

POLICY_SCHEMA = "flywheel.signer-policy/v1"
CONTEXT_NAME = "policy-context.json"
_CONTEXT_FIELDS = ("workspace", "allow_hosts", "owned_hosts", "fetch_hosts", "canaries",
                   "protected_paths")


class PolicyRequestError(ValueError):
    """The call to check is malformed."""


def receipt_args_sha256(args) -> str:
    """The digest tool_call_receipt.build_receipt computes for ``args``."""
    data = json.dumps(args, sort_keys=True, ensure_ascii=False).encode("utf-8") if args else b""
    return hashlib.sha256(data).hexdigest()


def load_context(home: Path) -> dict:
    path = Path(home) / CONTEXT_NAME
    raw = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    out = {"workspace": str(raw.get("workspace", ""))}
    for name in _CONTEXT_FIELDS[1:]:
        out[name] = sorted(str(v) for v in raw.get(name, []))
    return out


def evaluate(req: dict, context: dict) -> dict:
    """Run layer 1 of the shipped rule pack on one call. Returns the fields of
    the policy statement other than the signer's own."""
    from ..preaction.contract import ALLOW, ProposedCall, RunContext, worse
    from ..preaction.rules import evaluate as run_rules, load_pack, pack_digest
    tool, args, path_id = req.get("tool"), req.get("args"), req.get("path_id", "E1")
    if not isinstance(tool, str) or not tool or not isinstance(args, dict):
        raise PolicyRequestError("check_policy needs a tool name and an args object")
    if not isinstance(path_id, str):
        raise PolicyRequestError("path_id must be a string")
    pack = load_pack()
    call = ProposedCall(tool=tool, args=args, path_id=path_id)
    ctx = RunContext(workspace=context["workspace"],
                     **{k: tuple(context[k]) for k in _CONTEXT_FIELDS[1:]})
    verdict, hits = ALLOW, []
    for hit in run_rules(pack, call, ctx):
        verdict = worse(verdict, hit.action)
        hits.append(hit.id)
    ctx_digest = hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()
    return {"schema": POLICY_SCHEMA, "tool": tool, "path_id": path_id,
            "args_sha256": receipt_args_sha256(args), "call_sha256": call.call_sha256(),
            "rules_digest": pack_digest(pack), "context_sha256": ctx_digest,
            "verdict": verdict, "rule_hits": sorted(hits)}
