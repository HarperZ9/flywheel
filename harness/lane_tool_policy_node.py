"""Tool policy data for the Node lanes (learn 1.6.0, telos 0.4.1).

Plain data, merged into ``lane_tool_policy.LANE_TOOL_POLICY``; each entry holds
the ``ToolPolicy`` fields that differ from the default (T1, 20 s, no needs, not
main, in the build, effect ``read``). The tool names are exactly the ``static_tool_names``
pinned in ``packaging/node-lane-payloads.json``, measured from ``tools/list``
of the pinned archives.

Measured on the pinned archives (the review notes in
``project-docs/lanes/POLICY-REVIEW.md`` give the evidence):

- telos: held out of this build (the O-8 hold, POLICY-DECISION C-7), so every
  tool is ``NOT_IN_BUILD`` with slug ``release_on_hold`` and none is main. A
  contained telos release gets a new tool-by-tool review before any tool
  returns to T1. The notes below describe the held 0.4.1 archive: every MCP
  tool ignores its arguments and runs one fixed script of the
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

TELOS_NOT_IN_BUILD = {"telos.native.control": "actuation_outside_app"}
_TELOS_OUT = {
    "telos.native.control": {
        "tier": "T2", "effect": "actuate",
        "reason": "The Chrome DevTools and UI Automation driver; mail, post and listing "
                  "actions sit behind other arguments. Left out rather than admitted at T2."},
}
_TELOS_READ = ("Runs one fixed package script that reads files inside the package and "
               "prints JSON; the MCP mapping passes no arguments.")

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


_TELOS_HOLD = "release_on_hold"


def _telos_entry(name: str) -> dict:
    if name in TELOS_NOT_IN_BUILD:
        return {"not_in_build": TELOS_NOT_IN_BUILD[name], **_TELOS_OUT[name]}
    return {"reason": _TELOS_READ + " Held out of this build while its release contents "
                      "are reviewed.",
            "not_in_build": _TELOS_HOLD}


_READ = {"reason": "Reads a saved run or session in the lane folder, or a file the "
                  "caller names, and returns JSON."}
_SESSION = ("Writes one session file under <home>/lanes/learn/tutor/, the lane's own "
            "folder.")
_LEARN = {
    "learn_doctor": _READ, "learn_status": _READ, "learn_verify": _READ,
    "learn_receipt": _READ,
    "learn_dry_run": {**_MAIN, "reason": "Checks a workflow step by step without running "
                                         "it; reads the file the caller names."},
    "learn_tutor_plan": {**_MAIN, "effect": "state_write",
                         "reason": _SESSION + " The engine refuses a plan for a session "
                                              "that already has a file, so a T1 plan "
                                              "cannot reset what the T2 record wrote."},
    "learn_tutor_record": {"tier": "T2", "effect": "state_write",
                           "reason": _SESSION + " The policy review keeps it at T2."},
    "learn_tutor_mastery": _READ, "learn_visualize_dry_run": _READ, "learn_tutor_due": _READ,
    "learn_tutor_studyplan": _READ, "learn_tutor_misconceptions": _READ,
    "learn_tutor_reverify": _READ, "learn_tutor_derive_schedule": _READ,
    "learn_tutor_prooflesson": _READ,
}

# Every tool of both lanes runs under Node, so each needs the "node" setup item
# (met by the bundled runtime unless FLYWHEEL_NODE=none or it fails --version).
_NEEDS = {"needs": ("node",)}

NODE_LANE_POLICY: dict[str, dict[str, dict]] = {
    "learn": {name: {**_NEEDS, **fields} for name, fields in _LEARN.items()},
    "telos": {name: {**_NEEDS, **_telos_entry(name)} for name in _TELOS_TOOLS},
}
