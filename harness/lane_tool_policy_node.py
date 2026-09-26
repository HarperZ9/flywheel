"""Draft tool policy for the Node lanes (learn 1.6.0, telos 0.4.1). Operator review pending.

Plain data, merged into ``lane_tool_policy.LANE_TOOL_POLICY``; each entry holds
the ``ToolPolicy`` fields that differ from the default (T1, 20 s, no needs, not
main, in the build). The tool names are exactly the ``static_tool_names``
pinned in ``packaging/node-lane-payloads.json``, measured from ``tools/list``
of the pinned archives.

Measured on the pinned archives (the review notes in
``project-docs/lanes/POLICY-REVIEW.md`` give the evidence):

- telos: every MCP tool ignores its arguments and runs one fixed script of the
  package with fixed flags, so a tool's reach is its script. ``native.control``
  is the Chrome DevTools and Windows UI Automation driver (it also holds mail,
  post and listing actions behind other arguments), so the build leaves it out
  rather than admit it at T2. ``room`` and ``workflow`` shell out to ``python``
  and the sibling source checkouts, which an installed app does not have.
- learn: the crucible, gather and telos interop commands are CLI only in 1.6.0
  (``src/cli.mjs``); none of the 15 MCP tools reaches them, so no learn tool is
  out of the build for that reason. ``tutor_plan`` and ``tutor_record`` write a
  session file under the lane folder; the plan's draft keeps ``tutor_record``
  at T2 and the review asks whether the state-folder rule should make it T1.
"""
from __future__ import annotations

_MAIN = {"main": True}

TELOS_NOT_IN_BUILD = {
    "telos.native.control": "actuation_outside_app",
    "telos.room": "needs_source_checkouts",
    "telos.workflow": "needs_source_checkouts",
}

_TELOS_TOOLS = (
    "telos.status", "telos.doctor", "telos.room", "telos.workflow", "telos.catalog",
    "telos.server.manifest", "telos.mcp.freshness", "telos.ci.doctor", "telos.ci.triage",
    "telos.presentation.doctor", "telos.accessibility.doctor", "telos.performance.doctor",
    "telos.compatibility.doctor", "telos.operator.doctor", "telos.admission.telemetry",
    "telos.context.envelope", "telos.context.pack", "telos.action.receipt",
    "telos.loop.ledger", "telos.objective.monitor", "telos.model.foundry",
    "telos.learning.forge", "telos.learning.labs", "telos.research.seed",
    "telos.research.thermodynamic", "telos.rendering.research",
    "telos.rendering.capabilities", "telos.measurement.layers", "telos.creative.engine",
    "telos.creative.kernels", "telos.revival.registry", "telos.second_level.queue",
    "telos.workstation.substrate", "telos.display.calibration", "telos.native.control",
    "telos.browser.evidence", "telos.showcase.scout", "telos.proof", "telos.proof.research",
    "telos.proof.visual", "telos.proof.build",
)


def _telos_entry(name: str) -> dict:
    if name in TELOS_NOT_IN_BUILD:
        return {"not_in_build": TELOS_NOT_IN_BUILD[name]}
    return dict(_MAIN) if name in ("telos.catalog", "telos.doctor") else {}


_LEARN = {
    "learn_doctor": {}, "learn_status": {}, "learn_verify": {}, "learn_receipt": {},
    "learn_dry_run": _MAIN, "learn_tutor_plan": _MAIN,
    "learn_tutor_record": {"tier": "T2"},
    "learn_tutor_mastery": {}, "learn_visualize_dry_run": {}, "learn_tutor_due": {},
    "learn_tutor_studyplan": {}, "learn_tutor_misconceptions": {},
    "learn_tutor_reverify": {}, "learn_tutor_derive_schedule": {},
    "learn_tutor_prooflesson": {},
}

# Every tool of both lanes runs under Node, so each needs the "node" setup item
# (met by the bundled runtime unless FLYWHEEL_NODE=none or it fails --version).
_NEEDS = {"needs": ("node",)}

NODE_LANE_POLICY: dict[str, dict[str, dict]] = {
    "learn": {name: {**_NEEDS, **fields} for name, fields in _LEARN.items()},
    "telos": {name: {**_NEEDS, **_telos_entry(name)} for name in _TELOS_TOOLS},
}
