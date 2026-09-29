"""Tool policy data for the Node lanes (learn, and telos 0.4.2).

Plain data, merged into ``lane_tool_policy.LANE_TOOL_POLICY``; each entry holds
the ``ToolPolicy`` fields that differ from the default (T1, 20 s, no needs, not
main, in the build, effect ``read``). The tool names are exactly the ``static_tool_names``
pinned in ``packaging/node-lane-payloads.json``, measured from ``tools/list``
of the pinned archives.

Measured on the pinned archives (the review notes in
``project-docs/lanes/POLICY-REVIEW.md`` give the evidence):

- telos 0.4.2: every MCP tool ignores its arguments and runs one fixed package
  script with fixed flags (``demo/telos-mcp.mjs``, ``toolScripts``), so a tool's
  reach is its script. Each was read in the 0.4.2 source and measured with every
  call instrumented for processes, writes, reads and network use. 37 tools read
  the package (``presentation.doctor`` also reads the four sibling source
  folders) and print JSON: T1. ``room``, ``workflow`` and ``proof`` start
  programs from outside the package (python from PATH, the sibling source
  folders, a witness script), so they act on the machine and run only on a T2
  call. ``native.control`` is the Chrome DevTools, UI Automation and device
  driver; over MCP it prints its verb catalog, and the build still leaves it
  out. No tool used the network, a browser or the screen.
- learn: the crucible, gather and telos interop commands are CLI only in 1.6.0
  (``src/cli.mjs``); none of the 15 MCP tools reaches them, so no learn tool is
  out of the build for that reason. ``tutor_plan`` and ``tutor_record`` write a
  session file under the lane folder; the plan's draft keeps ``tutor_record``
  at T2 and the review asks whether the state-folder rule should make it T1.
"""
from __future__ import annotations

_MAIN = {"main": True}

_PKG = ("Runs one fixed package script that reads files inside the package and "
        "prints JSON; the MCP mapping passes no arguments.")
_PROGRAMS = " Programs outside the package run, so each call needs a T2 approval."
_TELOS = {
    "telos.status": {"reason": _PKG},
    "telos.doctor": {"reason": _PKG},
    "telos.room": {
        "tier": "T2", "effect": "actuate", "timeout_s": 60,
        "reason": "Starts the python found on PATH and, when gather, crucible, index and "
                  "forum source folders sit beside the package, runs their status and "
                  "doctor commands from those folders." + _PROGRAMS},
    "telos.workflow": {
        "tier": "T2", "effect": "actuate", "timeout_s": 60,
        "reason": "Starts the python found on PATH and, with the four source folders "
                  "beside the package, runs index map, gather docs, forum route and "
                  "crucible assess from them and a node from PATH; its temp files stay "
                  "in the lane folder." + _PROGRAMS},
    "telos.catalog": {**_MAIN, "reason": _PKG},
    "telos.server.manifest": {"reason": _PKG},
    "telos.mcp.freshness": {"reason": _PKG},
    "telos.ci.doctor": {"reason": _PKG},
    "telos.ci.triage": {"reason": "Triages the package's bundled CI fixture and prints "
                                  "JSON; the MCP mapping passes no arguments, so the "
                                  "live GitHub intake is never reached."},
    "telos.presentation.doctor": {
        "reason": "Reads the package and, read-only, the README, changelog and brand "
                  "files in gather, crucible, index and forum folders beside it; prints "
                  "JSON and writes nothing."},
    "telos.accessibility.doctor": {"reason": _PKG},
    "telos.performance.doctor": {"reason": _PKG},
    "telos.compatibility.doctor": {"reason": _PKG},
    "telos.operator.doctor": {
        "reason": "Runs one fixed package script, which also starts the package's own "
                  "status script on the same Node; reads files inside the package and "
                  "prints JSON."},
    "telos.admission.telemetry": {"reason": _PKG},
    "telos.context.envelope": {"reason": _PKG},
    "telos.context.pack": {"reason": _PKG},
    "telos.action.receipt": {"reason": _PKG},
    "telos.loop.ledger": {"reason": _PKG},
    "telos.objective.monitor": {"reason": _PKG},
    "telos.model.foundry": {"reason": _PKG},
    "telos.learning.forge": {"reason": _PKG},
    "telos.learning.labs": {"reason": _PKG},
    "telos.research.seed": {"reason": _PKG},
    "telos.research.thermodynamic": {"reason": _PKG},
    "telos.rendering.research": {"reason": _PKG},
    "telos.rendering.capabilities": {"reason": _PKG},
    "telos.measurement.layers": {"reason": _PKG},
    "telos.creative.engine": {"reason": _PKG},
    "telos.creative.kernels": {"reason": _PKG},
    "telos.revival.registry": {"reason": _PKG},
    "telos.second_level.queue": {"reason": _PKG},
    "telos.workstation.substrate": {"reason": _PKG},
    "telos.display.calibration": {"reason": "Returns a calibration contract from package "
                                            "data; changes no display setting."},
    "telos.native.control": {
        "tier": "T2", "effect": "actuate", "not_in_build": "actuation_outside_app",
        "reason": "The package's Chrome DevTools, UI Automation and device driver. With no "
                  "arguments it prints its verb catalog, but the script is the driver, so "
                  "the build leaves it out rather than admit it at T2."},
    "telos.browser.evidence": {"reason": "Returns the package's synthetic browser evidence "
                                         "fixture as JSON; starts no browser."},
    "telos.showcase.scout": {"reason": "Ranks the package's bundled scout fixture and "
                                       "prints JSON; the live GitHub search and the file "
                                       "output are not reachable from the MCP mapping."},
    "telos.proof": {
        "tier": "T2", "effect": "actuate",
        "reason": "Its witness stage runs node on the script TELOS_EMET_CLI names, or on "
                  "an emet folder beside the package, with temp files in the lane "
                  "folder." + _PROGRAMS},
    "telos.proof.research": {**_MAIN, "reason": "Assembles and verifies the bundled demo "
                                                "packet in memory; this proof has no "
                                                "witness stage and writes nothing."},
    "telos.proof.visual": {**_MAIN, "reason": "Recomputes the bundled demo packet's "
                                              "measurements in memory; no witness stage, "
                                              "no write."},
    "telos.proof.build": {**_MAIN, "reason": "Recomputes the bundled demo run's invariant "
                                             "in memory; no witness stage, no write."},
}


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
    "telos": {name: {**_NEEDS, **fields} for name, fields in _TELOS.items()},
}
