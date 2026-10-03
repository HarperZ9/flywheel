"""hook_setup.py -- build the monitor for one hook event from the owner's config.

Split out of hook_cli.py. The external hook runs one process per call, so each
event loads the owner config (owner.py), applies its hosts, canaries and
protected paths to the run context, checks the rule pack against the owner's
expected digest, gates the call, and exports the chain head to the owner's
witness directory at every stop and every N records. Any failure here raises,
and hook_cli turns a raise into a fail-closed deny.
"""
from __future__ import annotations

from . import owner as owner_mod
from .contract import ALLOW, BLOCK, Assessment, Hit, ProposedCall, RunContext, UNVERIFIABLE


class RulePackMismatch(RuntimeError):
    """The installed rule pack is not the one the owner expects."""


def load_owner(path):
    return owner_mod.load(path or None)


def build_monitor(home, owner):
    from .core import Monitor
    mon = Monitor(home=home, config=owner.monitor_config())
    if owner.expected_rules_digest and owner.expected_rules_digest != mon.rules_digest:
        raise RulePackMismatch(
            f"rule pack digest {mon.rules_digest[:12]} is not the owner's "
            f"{owner.expected_rules_digest[:12]}")
    return mon


def gate_event(home, call: ProposedCall, ctx: RunContext, owner, clock=None):
    """Gate one call with the owner's config applied; export the chain head
    when the owner set a witness directory. Returns the Gate."""
    from .witness import export_head
    try:
        mon = build_monitor(home, owner)
    except RulePackMismatch as exc:
        return _mismatch_gate(call, str(exc))
    gate = mon.gate(call, owner.apply(ctx))
    if owner.witness_dir:
        seq = mon.store._head()[1]
        if gate.verdict != ALLOW or seq % owner.head_export_every == 0:
            export_head(home, owner.witness_dir, clock=clock)
    return gate


def _mismatch_gate(call: ProposedCall, why: str):
    from .core import Gate
    asm = Assessment(verdict=BLOCK, path_id=call.path_id, coverage=UNVERIFIABLE)
    asm.reasons.append(Hit("rules_digest_mismatch", "monitor-tamper", BLOCK, why,
                           layer=0).to_dict())
    return Gate(BLOCK, False, asm, agent_text="blocked by policy rule rules_digest_mismatch")
